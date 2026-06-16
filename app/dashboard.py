import json
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import httpx
from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
from pydantic import BaseModel
from app.core.yt_pipeline import YTPipeline
from app.models.youtube import AnalyticsSnapshot
from app.models.content import ContentStatus
from app.config import settings
from app.services.youtube_service import YouTubeService


router = APIRouter(prefix="/api/v1/yt", tags=["youtube"])
pipeline = YTPipeline()


class CreateVideoRequest(BaseModel):
    topic: str
    target_audience: str = "general audience"
    video_length: str = "medium"
    tone: str = "professional"
    niche: str = "general"


class XPostRequest(BaseModel):
    thread: Optional[List[str]] = None
    text: Optional[str] = None


@router.post("/create")
async def create_video(request: CreateVideoRequest, background_tasks: BackgroundTasks):
    # Non-blocking: register the task, run the pipeline in the background, return the id immediately.
    # Clients poll GET /tasks/{task_id} until status is "completed" (the result is included there).
    task_id = pipeline.register_task()
    background_tasks.add_task(
        pipeline.create_video_content,
        topic=request.topic,
        target_audience=request.target_audience,
        video_length=request.video_length,
        tone=request.tone,
        niche=request.niche,
        task_id=task_id,
    )
    return {"task_id": task_id, "status": "processing"}


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    result = await pipeline.get_task_status(task_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


yt_service = YouTubeService()


@router.get("/channel")
async def get_channel():
    """Connected channel's stats + recent uploads (requires YouTube OAuth)."""
    stats = await yt_service.get_channel_stats()
    if isinstance(stats, dict) and stats.get("error"):
        raise HTTPException(status_code=503, detail=f"YouTube not connected: {stats['error']}")
    videos = await yt_service.list_channel_videos(max_results=10)
    return {
        "stats": stats,
        "recent_videos": [
            {
                "video_id": item.get("snippet", {}).get("resourceId", {}).get("videoId"),
                "title": item.get("snippet", {}).get("title"),
                "published_at": item.get("snippet", {}).get("publishedAt"),
                "thumbnails": item.get("snippet", {}).get("thumbnails"),
            }
            for item in videos[:10]
        ]
    }


@router.delete("/tasks/{task_id}")
async def cancel_task(task_id: str):
    result = await pipeline.cancel_task(task_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/tasks")
async def list_tasks():
    return {
        "active_tasks": [
            {"task_id": tid, **{k: v for k, v in info.items() if k != "result"}}
            for tid, info in pipeline.active_tasks.items()
        ]
    }


@router.post("/plan")
async def generate_plan(niche: str = Query(...), month: str = Query(None),
                         num_videos: int = Query(8), audience: str = Query("general audience")):
    month = month or datetime.now().strftime("%B %Y")
    result = await pipeline.generate_content_plan(niche, month, num_videos, audience)
    return result


@router.post("/batch")
async def batch_create(topics: List[str],
                        target_audience: str = Query("general audience"),
                        video_length: str = Query("medium"),
                        tone: str = Query("professional"),
                        niche: str = Query("general")):
    results = await pipeline.create_batch(
        topics=topics,
        target_audience=target_audience,
        video_length=video_length,
        tone=tone,
        niche=niche
    )
    return {
        "total": len(results),
        "success_count": sum(1 for r in results if r["status"] == "success"),
        "results": results
    }


@router.get("/videos")
async def list_videos(limit: int = Query(20), offset: int = Query(0)):
    """Persisted video results — these survive restarts when D1 is configured."""
    return await pipeline.db.list_yt_videos(limit=limit, offset=offset)


@router.get("/videos/{video_id}")
async def get_video(video_id: str):
    v = await pipeline.db.get_yt_video(video_id)
    if not v:
        raise HTTPException(status_code=404, detail="Video not found")
    return v


@router.get("/export/{task_id}")
async def export_script(task_id: str, format: str = Query("plain")):
    # In-memory first; fall back to the persisted store so exports survive a restart.
    task = pipeline.active_tasks.get(task_id)
    result = task.get("result") if task and task.get("status") == ContentStatus.COMPLETED else None
    if result is None:
        persisted = await pipeline.db.get_yt_video(task_id)
        result = persisted.get("result") if persisted else None
    if not result:
        raise HTTPException(status_code=404, detail="Task not found or not completed")

    script = result.get("script", {}) or {}
    if format == "plain":
        return {
            "task_id": task_id,
            "title": script.get("title", ""),
            "script": script.get("full_script", ""),
        }
    return {"task_id": task_id, "format": format, "result": result}


@router.get("/x/config")
async def x_config():
    """Tell the frontend whether X auto-post is wired and whether an account is connected.
    Returns no secrets — only the public login URL + connection status."""
    base = (settings.x_worker_url or "").rstrip("/")
    if not base:
        return {"configured": False, "connected": False, "login_url": None, "username": None}
    out = {"configured": True, "login_url": f"{base}/x/login", "connected": False, "username": None}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"{base}/x/status")
            if r.status_code == 200:
                d = r.json()
                out["connected"] = bool(d.get("connected"))
                out["username"] = d.get("username")
    except Exception:
        pass
    return out


@router.post("/x/post")
async def x_post(req: XPostRequest):
    """Proxy a thread/text to the x-worker. The worker token stays server-side (never in the browser)."""
    base = (settings.x_worker_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="X worker not configured (set X_WORKER_URL).")
    payload = {k: v for k, v in req.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="Provide 'thread' (list) or 'text' (string).")
    headers = {"Content-Type": "application/json"}
    if settings.x_worker_token:
        headers["Authorization"] = f"Bearer {settings.x_worker_token}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{base}/x/post", headers=headers, json=payload)
            try:
                data = r.json()
            except Exception:
                data = {"error": r.text}
            if r.status_code >= 400:
                raise HTTPException(status_code=r.status_code, detail=data.get("error") or data)
            return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"X worker request failed: {e}")
