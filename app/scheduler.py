import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from app.models.youtube import UploadSchedule, VideoStatus
from app.config import settings


SCHEDULE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "upload_schedule.json")


class Scheduler:
    def __init__(self):
        self.schedule: List[UploadSchedule] = []
        self._running = False
        self._load_schedule()

    def _load_schedule(self):
        if os.path.exists(SCHEDULE_FILE):
            try:
                with open(SCHEDULE_FILE) as f:
                    data = json.load(f)
                    self.schedule = [UploadSchedule(**item) for item in data]
            except Exception as e:
                print(f"Failed to load schedule: {e}")
                self.schedule = []

    def _save_schedule(self):
        try:
            with open(SCHEDULE_FILE, "w") as f:
                json.dump([s.model_dump() for s in self.schedule], f, indent=2, default=str)
        except Exception as e:
            print(f"Failed to save schedule: {e}")

    def add_upload(self, item: UploadSchedule) -> str:
        item.video_id = f"sched_{int(time.time())}_{len(self.schedule)}"
        self.schedule.append(item)
        self._save_schedule()
        return item.video_id

    def get_pending_uploads(self) -> List[UploadSchedule]:
        now = datetime.utcnow()
        return [
            s for s in self.schedule
            if s.status == VideoStatus.READY_TO_PUBLISH
            and s.publish_at and s.publish_at <= now
        ]

    def get_upcoming(self, days: int = 7) -> List[UploadSchedule]:
        now = datetime.utcnow()
        cutoff = now + timedelta(days=days)
        return [
            s for s in self.schedule
            if s.publish_at and now <= s.publish_at <= cutoff
            and s.status in [VideoStatus.READY_TO_PUBLISH, VideoStatus.SCHEDULED]
        ]

    def update_status(self, video_id: str, status: VideoStatus):
        for s in self.schedule:
            if s.video_id == video_id:
                s.status = status
                self._save_schedule()
                return

    async def run(self, check_interval: int = 300):
        self._running = True
        print(f"Scheduler started. Checking every {check_interval}s...")

        while self._running:
            try:
                pending = self.get_pending_uploads()
                for upload in pending:
                    print(f"Processing scheduled upload: {upload.video_id}")
                    self.update_status(upload.video_id, VideoStatus.PUBLISHING)

                    from app.services.youtube_service import YouTubeService
                    yt = YouTubeService()
                    meta = upload.metadata if hasattr(upload, 'metadata') else None

                    if meta:
                        result = await yt.upload_video(
                            video_path=f"videos/{upload.video_id}.mp4",
                            metadata=meta,
                            thumbnail_path=upload.thumbnail_path,
                            privacy_status=upload.privacy_status
                        )

                        if result["status"] == "success":
                            self.update_status(upload.video_id, VideoStatus.PUBLISHED)
                            print(f"Published: {result.get('video_url', '')}")
                        else:
                            self.update_status(upload.video_id, VideoStatus.FAILED)
                            print(f"Upload failed: {result.get('message', '')}")

                await asyncio.sleep(check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Scheduler error: {e}")
                await asyncio.sleep(check_interval)

    def stop(self):
        self._running = False
