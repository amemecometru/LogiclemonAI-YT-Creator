import json
import uuid
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.config import settings
from app.models.content import ContentRequest, ContentPiece, ContentStatus, AgentTask, QualityAssessment


class DatabaseService:
    def __init__(self):
        self._enabled = bool(settings.cloudflare_db_url and settings.cloudflare_api_token)
        if not self._enabled:
            print("Cloudflare DB not configured - running without database persistence")

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if settings.cloudflare_api_token:
            h["Authorization"] = f"Bearer {settings.cloudflare_api_token}"
        return h

    async def _post(self, path: str, data: dict) -> Optional[dict]:
        if not self._enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{settings.cloudflare_db_url}{path}", headers=self._headers(), json=data)
                return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            print(f"[DB] Request error: {e}")
            return None

    async def _get(self, path: str) -> Optional[dict]:
        if not self._enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{settings.cloudflare_db_url}{path}", headers=self._headers())
                return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            print(f"[DB] Request error: {e}")
            return None

    async def _patch(self, path: str, data: dict) -> Optional[dict]:
        if not self._enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.patch(f"{settings.cloudflare_db_url}{path}", headers=self._headers(), json=data)
                return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            print(f"[DB] Request error: {e}")
            return None

    async def create_content_request(self, request: ContentRequest) -> str:
        data = {
            "id": request.id or str(uuid.uuid4()),
            "user_id": request.user_id,
            "topic": request.topic,
            "content_type": request.content_type,
            "target_audience": request.target_audience,
            "style_requirements": request.style_requirements,
            "status": request.status,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        result = await self._post("/content_requests", data)
        if result:
            return result.get("id", data["id"])
        print(f"[DB] Mock create_content_request: {data['id']}")
        return data["id"]

    async def get_content_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        result = await self._get(f"/content_requests/{request_id}")
        return result

    async def update_content_request_status(self, request_id: str, status: ContentStatus) -> bool:
        result = await self._patch(f"/content_requests/{request_id}", {"status": status})
        if result:
            return result.get("success", False)
        return True

    async def create_content_piece(self, content_data: Dict[str, Any]) -> str:
        data = {
            "id": content_data.get("id", str(uuid.uuid4())),
            "request_id": content_data.get("request_id"),
            "title": content_data.get("title"),
            "content": content_data.get("content"),
            "metadata": content_data.get("metadata", {}),
            "quality_score": content_data.get("quality_score", 0.0),
            "seo_score": content_data.get("seo_score", 0.0),
            "fact_check_score": content_data.get("fact_check_score", 0.0),
            "status": content_data.get("status", ContentStatus.DRAFT),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        result = await self._post("/content_pieces", data)
        if result:
            return result.get("id", data["id"])
        print(f"[DB] Mock create_content_piece: {data['id']}")
        return data["id"]

    async def get_content_piece(self, content_id: str) -> Optional[Dict[str, Any]]:
        return await self._get(f"/content_pieces/{content_id}")

    async def get_content_pieces_by_request(self, request_id: str) -> List[Dict[str, Any]]:
        result = await self._get(f"/content_pieces?request_id={request_id}")
        if result:
            return result.get("data", [])
        return []

    async def update_content_piece(self, content_id: str, updates: Dict[str, Any]) -> bool:
        updates["updated_at"] = datetime.utcnow().isoformat()
        result = await self._patch(f"/content_pieces/{content_id}", updates)
        if result:
            return result.get("success", False)
        return True

    async def create_agent_task(self, task_data: Dict[str, Any]) -> str:
        data = {
            "id": task_data.get("id", str(uuid.uuid4())),
            "content_request_id": task_data.get("content_request_id"),
            "agent_type": task_data.get("agent_type"),
            "input_data": task_data.get("input_data", {}),
            "output_data": task_data.get("output_data", {}),
            "execution_time": task_data.get("execution_time", 0),
            "status": task_data.get("status", ContentStatus.PENDING),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        result = await self._post("/agent_tasks", data)
        if result:
            return result.get("id", data["id"])
        print(f"[DB] Mock create_agent_task: {data['id']}")
        return data["id"]

    async def update_agent_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        updates["updated_at"] = datetime.utcnow().isoformat()
        result = await self._patch(f"/agent_tasks/{task_id}", updates)
        if result:
            return result.get("success", False)
        return True

    async def get_agent_tasks_by_request(self, request_id: str) -> List[Dict[str, Any]]:
        result = await self._get(f"/agent_tasks?request_id={request_id}")
        if result:
            return result.get("data", [])
        return []

    async def create_quality_assessment(self, assessment_data: Dict[str, Any]) -> str:
        data = {
            "id": str(uuid.uuid4()),
            "content_id": assessment_data.get("content_id"),
            "assessment_type": assessment_data.get("assessment_type"),
            "score": assessment_data.get("score"),
            "details": assessment_data.get("details", {}),
            "assessed_at": datetime.utcnow().isoformat()
        }
        result = await self._post("/quality_assessments", data)
        if result:
            return result.get("id", data["id"])
        print(f"[DB] Mock create_quality_assessment: {data['id']}")
        return data["id"]

    async def get_quality_assessments(self, content_id: str) -> List[Dict[str, Any]]:
        result = await self._get(f"/quality_assessments?content_id={content_id}")
        if result:
            return result.get("data", [])
        return []

    async def list_content_requests(self, user_id: Optional[str] = None, limit: int = 10, offset: int = 0) -> Dict[str, Any]:
        params = f"?limit={limit}&offset={offset}"
        if user_id:
            params += f"&user_id={user_id}"
        result = await self._get(f"/content_requests{params}")
        if result:
            return result
        return {"data": [], "total": 0, "limit": limit, "offset": offset}

    async def get_content_with_request(self, content_id: str) -> Optional[Dict[str, Any]]:
        return await self._get(f"/content_with_request/{content_id}")

    async def get_content_stats(self) -> Dict[str, Any]:
        result = await self._get("/stats")
        if result:
            return result
        return {"total_requests": 0, "completed": 0, "failed": 0, "pending": 0, "success_rate": 0}

    async def save_yt_video(self, data: Dict[str, Any]) -> Optional[str]:
        payload = {
            "id": data.get("id") or str(uuid.uuid4()),
            "topic": data.get("topic"),
            "title": data.get("title"),
            "status": data.get("status", "completed"),
            "niche": data.get("niche"),
            "target_audience": data.get("target_audience"),
            "result": data.get("result", {}),
            "execution_time": data.get("execution_time", 0),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        result = await self._post("/yt_videos", payload)
        if result:
            return result.get("id", payload["id"])
        print(f"[DB] Mock save_yt_video: {payload['id']}")
        return None

    async def get_yt_video(self, video_id: str) -> Optional[Dict[str, Any]]:
        return await self._get(f"/yt_videos/{video_id}")

    async def list_yt_videos(self, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        result = await self._get(f"/yt_videos?limit={limit}&offset={offset}")
        if result:
            return result
        return {"data": [], "total": 0, "limit": limit, "offset": offset}

    async def health_check(self) -> bool:
        result = await self._get("/health")
        return result is not None and result.get("status") == "healthy"
