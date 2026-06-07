from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from enum import Enum


class VideoLength(str, Enum):
    SHORT = "short"        
    MEDIUM = "medium"      
    LONG = "long"         


class VideoStatus(str, Enum):
    DRAFT = "draft"
    SCRIPTS_READY = "scripts_ready"
    THUMBNAIL_READY = "thumbnail_ready"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    SCHEDULED = "scheduled"
    FAILED = "failed"


class ScriptSection(BaseModel):
    timestamp: str
    duration_seconds: int
    title: str
    content: str
    visual_cue: Optional[str] = None


class VideoScript(BaseModel):
    id: Optional[str] = None
    topic: str
    title: str
    hook: str
    sections: List[ScriptSection]
    conclusion: str
    call_to_action: str
    full_script: str
    estimated_duration_seconds: int
    word_count: int
    target_audience: str
    tone: str = "professional"
    key_points: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class YouTubeMetadata(BaseModel):
    title: str
    description: str
    tags: List[str]
    category_id: int = 22  
    language: str = "en"
    made_for_kids: bool = False
    recording_location: Optional[str] = None
    embeddable: bool = True
    public_stats_viewable: bool = True
    license: str = "youtube"
    privacy_status: str = "private"  

    model_config = {"use_enum_values": True}


class ThumbnailDesign(BaseModel):
    id: Optional[str] = None
    video_title: str
    concept_description: str
    composition_guide: str
    color_scheme: List[str]
    text_overlay: Optional[str] = None
    reference_images: List[str] = Field(default_factory=list)
    style_notes: str = ""
    ai_generation_prompt: Optional[str] = None


class ChannelNiche(BaseModel):
    name: str
    description: str
    target_audience: str
    content_categories: List[str]
    competition_keywords: List[str] = Field(default_factory=list)


class UploadSchedule(BaseModel):
    video_id: Optional[str] = None
    script_id: str
    publish_at: Optional[datetime] = None
    privacy_status: str = "private"
    thumbnail_path: Optional[str] = None
    status: VideoStatus = VideoStatus.DRAFT


class ContentPlan(BaseModel):
    id: Optional[str] = None
    channel_name: str
    niche: str
    month: str
    week: int
    videos: List[Dict[str, Any]] = Field(default_factory=list)
    status: str = "active"
    created_at: Optional[datetime] = None


class YouTubeChannelConfig(BaseModel):
    channel_id: str
    channel_name: str
    niche: str
    upload_schedule: str = "weekly"  
    preferred_upload_day: str = "saturday"
    preferred_upload_time: str = "14:00"
    video_length_preference: VideoLength = VideoLength.MEDIUM
    default_language: str = "en"
    default_category_id: int = 22
    brand_keywords: List[str] = Field(default_factory=list)
    brand_guidelines: str = ""


class AnalyticsSnapshot(BaseModel):
    video_id: str
    title: str
    views: int = 0
    likes: int = 0
    comments: int = 0
    avg_view_duration_percentage: float = 0.0
    impressions_click_through_rate: float = 0.0
    publish_date: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
