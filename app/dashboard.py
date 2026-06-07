import json
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from app.core.yt_pipeline import YTPipeline
from app.models.youtube import AnalyticsSnapshot


router = APIRouter(prefix="/api/v1/yt", tags=["youtube"])
pipeline = YTPipeline()


class CreateVideoRequest(BaseModel):
    topic: str
    target_audience: str = "general audience"
    video_length: str = "medium"
    tone: str = "professional"
    niche: str = "general"


@router.post("/create")
async def create_video(request: CreateVideoRequest):
    result = await pipeline.create_video_content(
        topic=request.topic,
        target_audience=request.target_audience,
        video_length=request.video_length,
        tone=request.tone,
        niche=request.niche
    )
    return result


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    result = await pipeline.get_task_status(task_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


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
            {
                "task_id": tid,
                **info
            }
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


@router.get("/export/{task_id}")
async def export_script(task_id: str, format: str = Query("plain")):
    task = pipeline.active_tasks.get(task_id)
    if not task or task["status"] not in ["completed", "COMPLETED", "completed"]:
        raise HTTPException(status_code=404, detail="Task not found or not completed")

    try:
        tid_int = int(task_id.split("_")[1])
    except (IndexError, ValueError):
        raise HTTPException(status_code=404, detail="Cannot retrieve script for this task")

    return {"error": "Script data not available for this task. Use create endpoint directly."}
