"""Main FastAPI application for LogiclemonAI - Content Creator Pipeline."""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Dict, Any
import time
import uuid
import os
from datetime import datetime
from app.config import settings
from app.models.content import ContentRequest, ContentType, ContentStatus
from app.core.orchestrator import ContentOrchestrator
from app.core.yt_pipeline import YTPipeline
from app.services.database_service import DatabaseService
from app.dashboard import router as yt_router

app = FastAPI(
    title="LogiclemonAI - Content Creator",
    version=settings.app_version,
    description="AI-powered YouTube content creation pipeline with multi-agent system"
)

# CORS: "*" origins + credentials=True is rejected by browsers and is insecure. This API
# authenticates via header API keys (not cookies), so credentials are only enabled when
# explicit origins are configured via CORS_ALLOW_ORIGINS.
_cors_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = ContentOrchestrator()
yt_pipeline = YTPipeline()
db_service = DatabaseService()

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/dashboard", StaticFiles(directory=static_dir, html=True), name="dashboard")

app.include_router(yt_router)


@app.get("/")
async def root():
    return {
        "message": "LogiclemonAI - Content Creator API",
        "version": settings.app_version,
        "status": "running",
        "endpoints": {
            "create_content": "/api/v1/content/create",
            "get_content": "/api/v1/content/{content_id}",
            "get_status": "/api/v1/content/{content_id}/status",
            "health": "/health",
            "yt_create": "/api/v1/yt/create",
            "yt_plan": "/api/v1/yt/plan",
            "yt_tasks": "/api/v1/yt/tasks",
            "yt_batch": "/api/v1/yt/batch",
            "dashboard": "/dashboard"
        }
    }


@app.get("/health")
async def health_check():
    db_healthy = await db_service.health_check()
    return {
        "status": "healthy" if db_healthy else "degraded",
        "timestamp": time.time(),
        "version": settings.app_version,
        "database": "connected" if db_healthy else "disconnected",
        "pipelines": {
            "content": "ready",
            "youtube": "ready"
        }
    }


@app.post("/api/v1/content/create")
async def create_content(request: ContentRequest, background_tasks: BackgroundTasks):
    try:
        request_id = str(uuid.uuid4())
        request.id = request_id

        if not request.topic or len(request.topic.strip()) < 3:
            raise HTTPException(status_code=400, detail="Topic must be at least 3 characters")

        if request.word_count and (request.word_count < 100 or request.word_count > settings.max_content_length):
            raise HTTPException(status_code=400, detail=f"Word count must be between 100 and {settings.max_content_length}")

        await db_service.create_content_request(request)
        background_tasks.add_task(process_content_creation, request_id, request)

        return {
            "message": "Content creation started",
            "request_id": request_id,
            "status": ContentStatus.PENDING,
            "estimated_completion": "2-5 minutes"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start: {str(e)}")


@app.get("/api/v1/content/{content_id}")
async def get_content(content_id: str):
    content_data = await db_service.get_content_piece(content_id)
    if not content_data:
        request_data = await db_service.get_content_request(content_id)
        if not request_data:
            raise HTTPException(status_code=404, detail="Content not found")
        content_pieces = await db_service.get_content_pieces_by_request(content_id)
        return {
            "content_id": content_id,
            "status": request_data["status"],
            "created_at": request_data["created_at"],
            "request": request_data,
            "content_pieces": content_pieces
        }

    request_data = await db_service.get_content_request(content_data["request_id"]) if content_data.get("request_id") else None
    return {
        "content_id": content_id,
        "status": content_data["status"],
        "created_at": content_data["created_at"],
        "request": request_data,
        "result": {
            "status": "success" if content_data["status"] == ContentStatus.COMPLETED else "processing",
            "content": {
                "title": content_data["title"],
                "content": content_data["content"],
                "metadata": content_data["metadata"],
                "quality_metrics": {
                    "overall_quality": content_data["quality_score"],
                    "seo_score": content_data["seo_score"],
                    "fact_check_score": content_data["fact_check_score"]
                }
            }
        }
    }


@app.get("/api/v1/content/{content_id}/status")
async def get_content_status(content_id: str):
    task_status = await orchestrator.get_task_status(content_id)
    if "error" not in task_status:
        return task_status

    request_data = await db_service.get_content_request(content_id)
    if not request_data:
        raise HTTPException(status_code=404, detail="Content not found")

    created_at = datetime.fromisoformat(request_data["created_at"].replace('Z', '+00:00'))
    elapsed_time = (datetime.utcnow() - created_at.replace(tzinfo=None)).total_seconds()

    return {
        "request_id": content_id,
        "status": request_data["status"],
        "progress": 100 if request_data["status"] == ContentStatus.COMPLETED else 0,
        "elapsed_time": elapsed_time
    }


@app.delete("/api/v1/content/{content_id}")
async def cancel_content_creation(content_id: str):
    request_data = await db_service.get_content_request(content_id)
    if not request_data:
        raise HTTPException(status_code=404, detail="Content not found")

    await orchestrator.cancel_task(content_id)
    await db_service.update_content_request_status(content_id, ContentStatus.FAILED)

    return {"message": "Content creation cancelled", "content_id": content_id, "status": "cancelled"}


@app.get("/api/v1/content")
async def list_content(limit: int = 10, offset: int = 0, user_id: str = None):
    result = await db_service.list_content_requests(user_id=user_id, limit=limit, offset=offset)
    return {
        "total": result["total"],
        "limit": limit,
        "offset": offset,
        "content": [
            {
                "content_id": item["id"],
                "status": item["status"],
                "topic": item["topic"],
                "content_type": item["content_type"],
                "target_audience": item["target_audience"],
                "created_at": item["created_at"]
            }
            for item in result["data"]
        ]
    }


@app.get("/api/v1/stats")
async def get_stats():
    return await db_service.get_content_stats()


async def process_content_creation(request_id: str, request: ContentRequest):
    try:
        await db_service.update_content_request_status(request_id, ContentStatus.PROCESSING)
        result = await orchestrator.create_content(request)

        if result["status"] == "success":
            content_data = result["content"]
            content_piece_data = {
                "request_id": request_id,
                "title": content_data.get("title"),
                "content": content_data.get("content"),
                "metadata": content_data.get("metadata", {}),
                "quality_score": content_data.get("quality_metrics", {}).get("overall_quality", 0.0),
                "seo_score": content_data.get("quality_metrics", {}).get("seo_score", 0.0),
                "fact_check_score": content_data.get("quality_metrics", {}).get("fact_check_score", 0.0),
                "status": ContentStatus.COMPLETED
            }
            await db_service.create_content_piece(content_piece_data)
            await db_service.update_content_request_status(request_id, ContentStatus.COMPLETED)
        else:
            await db_service.update_content_request_status(request_id, ContentStatus.FAILED)
    except Exception as e:
        await db_service.update_content_request_status(request_id, ContentStatus.FAILED)
        print(f"Content creation failed for {request_id}: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
