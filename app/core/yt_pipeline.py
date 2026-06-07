import asyncio
import time
import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from app.agents.research_agent import ResearchAgent
from app.agents.script_writer_agent import ScriptWriterAgent
from app.agents.youtube_seo_agent import YouTubeSEOAgent
from app.agents.thumbnail_agent import ThumbnailAgent
from app.models.content import ContentRequest, ContentStatus
from app.models.youtube import VideoScript, YouTubeMetadata, ThumbnailDesign, ContentPlan
from app.config import settings


class YTPipeline:
    def __init__(self):
        self.research_agent = ResearchAgent()
        self.script_agent = ScriptWriterAgent()
        self.seo_agent = YouTubeSEOAgent()
        self.thumbnail_agent = ThumbnailAgent()
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.content_plan: Optional[ContentPlan] = None

    async def create_video_content(self, topic: str, target_audience: str = "general audience",
                                    video_length: str = "medium", tone: str = "professional",
                                    niche: str = "general", channel_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        task_id = f"yt_{int(time.time())}"
        self.active_tasks[task_id] = {
            "status": ContentStatus.PROCESSING,
            "start_time": time.time(),
            "current_agent": None,
            "progress": 0
        }

        try:
            self.active_tasks[task_id]["current_agent"] = "research"
            self.active_tasks[task_id]["progress"] = 5
            research_result = await self.research_agent.execute({
                "topic": topic,
                "max_results": 10,
                "search_depth": "advanced"
            })

            if research_result["status"] != "success":
                return self._error_response(task_id, "Research failed", research_result.get("message", ""))

            research_data = research_result.get("research_data", {})
            confidence = research_result.get("confidence_score", 0.5)
            self.active_tasks[task_id]["progress"] = 25

            self.active_tasks[task_id]["current_agent"] = "script_writer"
            self.active_tasks[task_id]["progress"] = 30
            script_result = await self.script_agent.execute({
                "topic": topic,
                "research_data": research_data,
                "target_audience": target_audience,
                "video_length": video_length,
                "tone": tone
            })

            if script_result["status"] != "success":
                return self._error_response(task_id, "Script writing failed", script_result.get("message", ""))

            script = script_result.get("script", {})
            self.active_tasks[task_id]["progress"] = 55

            self.active_tasks[task_id]["current_agent"] = "seo"
            self.active_tasks[task_id]["progress"] = 60
            seo_result = await self.seo_agent.execute({
                "topic": topic,
                "script": script,
                "research_data": research_data,
                "target_audience": target_audience,
                "channel_config": channel_config or {}
            })

            if seo_result["status"] != "success":
                return self._error_response(task_id, "SEO optimization failed", seo_result.get("message", ""))

            metadata = seo_result.get("metadata", {})
            title_variants = seo_result.get("title_variants", [])
            self.active_tasks[task_id]["progress"] = 80

            self.active_tasks[task_id]["current_agent"] = "thumbnail"
            self.active_tasks[task_id]["progress"] = 85
            thumbnail_result = await self.thumbnail_agent.execute({
                "topic": topic,
                "title": script.get("title", topic),
                "script": script,
                "research_data": research_data,
                "niche": niche
            })

            thumbnail = thumbnail_result.get("thumbnail", {}) if thumbnail_result["status"] == "success" else None
            self.active_tasks[task_id]["progress"] = 95

            execution_time = time.time() - self.active_tasks[task_id]["start_time"]

            result = {
                "task_id": task_id,
                "status": "success",
                "topic": topic,
                "execution_time": round(execution_time, 2),
                "research_confidence": round(confidence, 2),
                "script": script,
                "metadata": metadata,
                "title_variants": title_variants,
                "thumbnail_design": thumbnail,
                "research_data": {
                    "key_findings": research_data.get("key_findings", [])[:5],
                    "source_count": len(research_data.get("sources", [])),
                    "confidence": confidence
                }
            }

            self.active_tasks[task_id]["status"] = ContentStatus.COMPLETED
            self.active_tasks[task_id]["progress"] = 100

            return result

        except Exception as e:
            return self._error_response(task_id, "Pipeline execution failed", str(e))

    async def create_batch(self, topics: List[str], target_audience: str = "general audience",
                            video_length: str = "medium", tone: str = "professional",
                            niche: str = "general") -> List[Dict[str, Any]]:
        results = []
        for topic in topics:
            print(f"\nCreating video content for: {topic}")
            result = await self.create_video_content(
                topic=topic,
                target_audience=target_audience,
                video_length=video_length,
                tone=tone,
                niche=niche
            )
            results.append(result)
            if result["status"] != "success":
                print(f"Failed: {result.get('message', '')}")
        return results

    async def generate_content_plan(self, niche: str, month: str, num_videos: int = 8,
                                     target_audience: str = "general audience") -> Dict[str, Any]:
        prompt = f"""Create a YouTube content plan for a channel about "{niche}".

Generate {num_videos} video topics for {month}.

For each video provide:
1. Video title
2. Target keywords
3. Why it will perform well
4. Suggested video length

Return as JSON array:
[
  {{
    "title": "Video title",
    "keywords": ["keyword1", "keyword2"],
    "rationale": "Why this topic works",
    "suggested_length": "medium",
    "tone": "professional"
  }}
]

Return ONLY valid JSON."""

        from app.config import get_agent_config
        agent_cfg = get_agent_config()

        try:
            import openai
            client_kwargs = {"api_key": agent_cfg["openai_api_key"]}
            if agent_cfg.get("base_url"):
                client_kwargs["base_url"] = agent_cfg["base_url"]
            if agent_cfg.get("default_headers"):
                client_kwargs["default_headers"] = agent_cfg["default_headers"]
            client = openai.AsyncOpenAI(**client_kwargs)
            response = await client.chat.completions.create(
                model=agent_cfg["model"],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.8
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            video_plan = json.loads(content.strip())
        except Exception as e:
            print(f"Failed to generate content plan via AI: {e}")
            video_plan = [{"title": f"Video {i+1} about {niche}", "keywords": [niche],
                           "rationale": f"Educational content about {niche}", "suggested_length": "medium", "tone": "professional"}
                          for i in range(num_videos)]

        plan = ContentPlan(
            channel_name=niche.replace(" ", "_").lower(),
            niche=niche,
            month=month,
            week=1,
            videos=video_plan
        )

        return {
            "status": "success",
            "plan": plan.model_dump()
        }

    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        if task_id not in self.active_tasks:
            return {"error": "Task not found"}
        task = self.active_tasks[task_id]
        return {
            "task_id": task_id,
            "status": task["status"],
            "progress": task["progress"],
            "current_agent": task.get("current_agent"),
            "elapsed_time": round(time.time() - task["start_time"], 2)
        }

    async def cancel_task(self, task_id: str) -> Dict[str, Any]:
        if task_id not in self.active_tasks:
            return {"error": "Task not found"}
        self.active_tasks[task_id]["status"] = ContentStatus.FAILED
        return {"task_id": task_id, "status": "cancelled"}

    def _error_response(self, task_id: str, error_type: str, message: str) -> Dict[str, Any]:
        if task_id in self.active_tasks:
            self.active_tasks[task_id]["status"] = ContentStatus.FAILED
        return {
            "status": "error",
            "task_id": task_id,
            "error_type": error_type,
            "message": message
        }
