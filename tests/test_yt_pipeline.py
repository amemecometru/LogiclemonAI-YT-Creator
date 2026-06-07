import pytest
from unittest.mock import AsyncMock, patch
from app.core.yt_pipeline import YTPipeline
from app.models.youtube import VideoScript, ScriptSection, YouTubeMetadata, ThumbnailDesign


class TestYTPipeline:
    @pytest.fixture
    def pipeline(self):
        return YTPipeline()

    @pytest.mark.asyncio
    async def test_pipeline_initialization(self, pipeline):
        assert hasattr(pipeline, 'research_agent')
        assert hasattr(pipeline, 'script_agent')
        assert hasattr(pipeline, 'seo_agent')
        assert hasattr(pipeline, 'thumbnail_agent')
        assert hasattr(pipeline, 'active_tasks')

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self, pipeline):
        result = await pipeline.get_task_status("non-existent")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_cancel_task_not_found(self, pipeline):
        result = await pipeline.cancel_task("non-existent")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_create_video_content_research_fails(self, pipeline):
        with patch.object(pipeline.research_agent, 'execute', new=AsyncMock(return_value={
            "status": "error", "message": "Research failed"
        })):
            result = await pipeline.create_video_content("test topic")
            assert result["status"] == "error"
            assert "Research failed" in result["error_type"]

    @pytest.mark.asyncio
    async def test_error_response_structure(self, pipeline):
        error = pipeline._error_response("test-123", "TestError", "Something went wrong")
        assert error["status"] == "error"
        assert error["task_id"] == "test-123"
        assert error["error_type"] == "TestError"
        assert error["message"] == "Something went wrong"

    @pytest.mark.asyncio
    async def test_task_tracking(self, pipeline):
        task_id = "test-track-1"
        pipeline.active_tasks[task_id] = {
            "status": "processing",
            "progress": 50,
            "current_agent": "writer",
            "start_time": 1000.0
        }
        status = await pipeline.get_task_status(task_id)
        assert status["task_id"] == task_id
        assert status["progress"] == 50
        assert status["current_agent"] == "writer"


class TestVideoScript:
    def test_script_section_creation(self):
        section = ScriptSection(
            timestamp="0:00",
            duration_seconds=60,
            title="Introduction",
            content="Welcome to this video!",
            visual_cue="Title screen"
        )
        assert section.timestamp == "0:00"
        assert section.duration_seconds == 60
        assert "Introduction" in section.title

    def test_video_script_creation(self):
        sections = [
            ScriptSection(timestamp="0:00", duration_seconds=30, title="Hook", content="Hook content"),
            ScriptSection(timestamp="0:30", duration_seconds=120, title="Main", content="Main content"),
        ]
        script = VideoScript(
            topic="Test Topic",
            title="Test Title",
            hook="Test hook",
            sections=sections,
            conclusion="Test conclusion",
            call_to_action="Like and subscribe",
            full_script="Full script content",
            estimated_duration_seconds=150,
            word_count=500,
            target_audience="testers",
            tone="professional",
            key_points=["Point 1", "Point 2"]
        )
        assert script.title == "Test Title"
        assert len(script.sections) == 2
        assert script.estimated_duration_seconds == 150

    def test_metadata_creation(self):
        meta = YouTubeMetadata(
            title="Test Video",
            description="Test description with chapters\n\n0:00 - Intro",
            tags=["test", "video", "tutorial"],
            category_id=22
        )
        assert meta.title == "Test Video"
        assert len(meta.tags) == 3
        assert meta.category_id == 22
        assert meta.privacy_status == "private"

    def test_thumbnail_design_defaults(self):
        thumb = ThumbnailDesign(
            video_title="Test Video",
            concept_description="A bold thumbnail concept",
            composition_guide="Center focus",
            color_scheme=["#FF0000", "#000000"],
        )
        assert thumb.text_overlay is None
        assert thumb.style_notes == ""
        assert len(thumb.color_scheme) == 2


class TestMetadataDefaults:
    def test_youtube_metadata_defaults(self):
        meta = YouTubeMetadata(
            title="Title",
            description="Desc",
            tags=["tag1"]
        )
        assert meta.category_id == 22
        assert meta.language == "en"
        assert meta.made_for_kids is False
        assert meta.embeddable is True
        assert meta.privacy_status == "private"

    def test_content_plan_structure(self):
        from app.models.youtube import ContentPlan
        plan = ContentPlan(
            channel_name="test_channel",
            niche="technology",
            month="June 2025",
            week=2,
            videos=[{"title": "Video 1", "keywords": ["tech"]}]
        )
        assert plan.niche == "technology"
        assert len(plan.videos) == 1
        assert plan.videos[0]["title"] == "Video 1"

    def test_video_status_enum(self):
        from app.models.youtube import VideoStatus
        assert VideoStatus.DRAFT.value == "draft"
        assert VideoStatus.PUBLISHED.value == "published"
        assert VideoStatus.SCHEDULED.value == "scheduled"

    def test_video_length_enum(self):
        from app.models.youtube import VideoLength
        assert VideoLength.SHORT.value == "short"
        assert VideoLength.MEDIUM.value == "medium"
        assert VideoLength.LONG.value == "long"
