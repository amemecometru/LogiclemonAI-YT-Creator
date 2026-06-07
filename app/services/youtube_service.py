import os
import pickle
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from app.models.youtube import YouTubeMetadata, AnalyticsSnapshot, UploadSchedule


SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtubepartner",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


class YouTubeService:
    def __init__(self):
        self.api_service_name = "youtube"
        self.api_version = "v3"
        self.client_secret_file = os.getenv("YT_CLIENT_SECRET_FILE", "client_secret.json")
        self.token_file = os.getenv("YT_TOKEN_FILE", "yt_token.pickle")
        self.credentials = None
        self.service = None

    def _authenticate(self):
        if self.service:
            return self.service

        if os.path.exists(self.token_file):
            with open(self.token_file, "rb") as token:
                self.credentials = pickle.load(token)

        if not self.credentials or not self.credentials.valid:
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                self.credentials.refresh(Request())
            else:
                if not os.path.exists(self.client_secret_file):
                    print("YouTube client_secret.json not found. YouTube upload will be unavailable.")
                    return None
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secret_file, SCOPES)
                self.credentials = flow.run_local_server(port=0)

            with open(self.token_file, "wb") as token:
                pickle.dump(self.credentials, token)

        self.service = build(self.api_service_name, self.api_version, credentials=self.credentials)
        return self.service

    async def upload_video(self, video_path: str, metadata: YouTubeMetadata,
                            thumbnail_path: Optional[str] = None,
                            privacy_status: str = "private") -> Dict[str, Any]:
        service = self._authenticate()
        if not service:
            return {
                "status": "error",
                "message": "YouTube API not authenticated. Configure client_secret.json."
            }

        if not os.path.exists(video_path):
            return {"status": "error", "message": f"Video file not found: {video_path}"}

        body = {
            "snippet": {
                "title": metadata.title,
                "description": metadata.description,
                "tags": metadata.tags,
                "categoryId": str(metadata.category_id),
                "defaultLanguage": metadata.language,
            },
            "status": {
                "privacyStatus": privacy_status,
                "madeForKids": metadata.made_for_kids,
                "embeddable": metadata.embeddable,
                "publicStatsViewable": metadata.public_stats_viewable,
                "license": metadata.license,
                "selfDeclaredMadeForKids": metadata.made_for_kids,
            },
        }

        try:
            media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
            request = service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"Upload progress: {int(status.progress() * 100)}%")

            video_id = response.get("id")
            print(f"Upload successful! Video ID: {video_id}")

            if thumbnail_path and os.path.exists(thumbnail_path):
                await self._set_thumbnail(video_id, thumbnail_path)

            return {
                "status": "success",
                "video_id": video_id,
                "video_url": f"https://youtu.be/{video_id}",
                "uploaded_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {"status": "error", "message": f"YouTube upload failed: {str(e)}"}

    async def _set_thumbnail(self, video_id: str, thumbnail_path: str) -> bool:
        service = self._authenticate()
        if not service:
            return False

        try:
            service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path)
            ).execute()
            print(f"Thumbnail set for video {video_id}")
            return True
        except Exception as e:
            print(f"Failed to set thumbnail: {e}")
            return False

    async def update_video_metadata(self, video_id: str, metadata: YouTubeMetadata) -> Dict[str, Any]:
        service = self._authenticate()
        if not service:
            return {"status": "error", "message": "YouTube API not authenticated"}

        try:
            body = {
                "snippet": {
                    "title": metadata.title,
                    "description": metadata.description,
                    "tags": metadata.tags,
                    "categoryId": str(metadata.category_id),
                }
            }
            service.videos().update(part="snippet", body=body).execute()
            return {"status": "success", "video_id": video_id}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def schedule_video(self, video_path: str, metadata: YouTubeMetadata,
                              publish_at: datetime,
                              thumbnail_path: Optional[str] = None) -> Dict[str, Any]:
        now = datetime.utcnow()
        if publish_at <= now:
            return {"status": "error", "message": "Publish time must be in the future"}

        return await self.upload_video(
            video_path=video_path,
            metadata=metadata,
            thumbnail_path=thumbnail_path,
            privacy_status="private"
        )

    async def get_video_analytics(self, video_id: str) -> Optional[AnalyticsSnapshot]:
        service = self._authenticate()
        if not service:
            return None

        try:
            video_response = service.videos().list(
                part="statistics,snippet",
                id=video_id
            ).execute()

            if not video_response.get("items"):
                return None

            item = video_response["items"][0]
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})

            return AnalyticsSnapshot(
                video_id=video_id,
                title=snippet.get("title", ""),
                views=int(stats.get("viewCount", 0)),
                likes=int(stats.get("likeCount", 0)),
                comments=int(stats.get("commentCount", 0)),
                publish_date=datetime.fromisoformat(snippet.get("publishedAt", "").replace("Z", "+00:00")) if snippet.get("publishedAt") else None,
                fetched_at=datetime.utcnow()
            )

        except Exception as e:
            print(f"Error fetching analytics: {e}")
            return None

    async def list_channel_videos(self, max_results: int = 50) -> List[Dict[str, Any]]:
        service = self._authenticate()
        if not service:
            return []

        try:
            channel_response = service.channels().list(part="contentDetails", mine=True).execute()
            if not channel_response.get("items"):
                return []

            uploads_id = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

            videos = []
            next_page_token = None

            while len(videos) < max_results:
                request = service.playlistItems().list(
                    part="snippet",
                    playlistId=uploads_id,
                    max_results=min(50, max_results - len(videos)),
                    pageToken=next_page_token
                )
                response = request.execute()
                videos.extend(response.get("items", []))
                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    break

            return videos[:max_results]

        except Exception as e:
            print(f"Error listing videos: {e}")
            return []

    async def get_channel_stats(self) -> Dict[str, Any]:
        service = self._authenticate()
        if not service:
            return {"error": "Not authenticated"}

        try:
            response = service.channels().list(
                part="statistics,snippet",
                mine=True
            ).execute()

            if not response.get("items"):
                return {"error": "No channel found"}

            channel = response["items"][0]
            stats = channel.get("statistics", {})

            return {
                "channel_name": channel["snippet"]["title"],
                "subscriber_count": int(stats.get("subscriberCount", 0)),
                "view_count": int(stats.get("viewCount", 0)),
                "video_count": int(stats.get("videoCount", 0)),
            }
        except Exception as e:
            return {"error": str(e)}

    async def add_video_to_playlist(self, video_id: str, playlist_id: str) -> bool:
        service = self._authenticate()
        if not service:
            return False

        try:
            service.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id
                        }
                    }
                }
            ).execute()
            return True
        except Exception as e:
            print(f"Error adding to playlist: {e}")
            return False
