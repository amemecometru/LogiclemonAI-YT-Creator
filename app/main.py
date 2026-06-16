"""Main FastAPI application for LogiclemonAI — YouTube Content Creator."""

import os
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.services.database_service import DatabaseService
from app.dashboard import router as yt_router

app = FastAPI(
    title="LogiclemonAI - Content Creator",
    version=settings.app_version,
    description="AI-powered YouTube content creation pipeline with multi-agent system",
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

db_service = DatabaseService()

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/dashboard", StaticFiles(directory=static_dir, html=True), name="dashboard")

app.include_router(yt_router)


@app.get("/")
async def root():
    return {
        "message": "LogiclemonAI - YouTube Content Creator API",
        "version": settings.app_version,
        "status": "running",
        "endpoints": {
            "health": "/health",
            "yt_create": "/api/v1/yt/create",
            "yt_tasks": "/api/v1/yt/tasks",
            "yt_plan": "/api/v1/yt/plan",
            "yt_batch": "/api/v1/yt/batch",
            "yt_videos": "/api/v1/yt/videos",
            "yt_channel": "/api/v1/yt/channel",
            "api_keys": "/api/v1/yt/keys",
            "x_config": "/api/v1/yt/x/config",
            "dashboard": "/dashboard",
        },
    }


@app.get("/health")
async def health_check():
    db_healthy = await db_service.health_check()
    return {
        "status": "healthy" if db_healthy else "degraded",
        "timestamp": time.time(),
        "version": settings.app_version,
        "database": "connected" if db_healthy else "disconnected",
        "pipeline": "youtube",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
