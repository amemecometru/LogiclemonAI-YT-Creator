"""Test configuration and fixtures."""

import pytest
import asyncio
from unittest.mock import AsyncMock
import os

# Set test environment variables
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["DATABASE_URL"] = "sqlite:///test.db"
os.environ["CLOUDFLARE_API_TOKEN"] = "test-token"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response."""
    return "This is a mock response from OpenAI API."


@pytest.fixture
def sample_research_data():
    """Sample research data for testing."""
    return {
        "key_findings": [
            "AI is transforming healthcare",
            "Machine learning improves diagnosis accuracy",
            "AI reduces medical errors"
        ],
        "main_arguments": [
            "AI enhances patient care",
            "AI reduces healthcare costs"
        ],
        "sources": [
            {
                "title": "AI in Healthcare Study",
                "url": "https://example.com/study",
                "source": "Medical Journal",
                "credibility_score": 0.9
            }
        ],
        "statistics": [
            {
                "statistic": "AI improves diagnosis accuracy",
                "value": "95%",
                "source": "Medical Research"
            }
        ],
        "expert_opinions": [
            {
                "opinion": "AI will revolutionize healthcare",
                "expert": "Dr. Smith",
                "source": "Healthcare Today"
            }
        ],
        "confidence_score": 0.8
    }


@pytest.fixture
def sample_writing_output():
    """Sample writing output for testing."""
    return {
        "title": "AI in Healthcare: Transforming Patient Care",
        "content": """# AI in Healthcare: Transforming Patient Care

## Introduction

Artificial Intelligence is revolutionizing the healthcare industry by improving diagnosis accuracy and reducing medical errors.

## Benefits of AI in Healthcare

AI provides numerous benefits including enhanced patient care and reduced healthcare costs.

## Conclusion

The future of healthcare lies in the integration of AI technologies.""",
        "outline": {
            "title": "AI in Healthcare: Transforming Patient Care",
            "introduction": {
                "hook": "AI is revolutionizing healthcare",
                "overview": "Learn about AI benefits in healthcare"
            },
            "main_sections": [
                {
                    "title": "Benefits of AI in Healthcare",
                    "subsections": ["Enhanced Care", "Cost Reduction"]
                }
            ]
        },
        "word_count": 150,
        "estimated_reading_time": 1,
        "metadata": {
            "title": "AI in Healthcare: Transforming Patient Care",
            "meta_description": "Learn how AI is transforming healthcare through improved diagnosis and patient care.",
            "keywords": ["AI", "healthcare", "artificial intelligence", "patient care"],
            "language": "en",
            "content_type": "article"
        }
    }


@pytest.fixture
def sample_youtube_script():
    """Sample YouTube script for testing."""
    from app.models.youtube import VideoScript, ScriptSection
    return VideoScript(
        topic="AI in Healthcare",
        title="How AI is Revolutionizing Healthcare",
        hook="What if I told you AI can detect diseases before symptoms appear?",
        sections=[
            ScriptSection(timestamp="0:00", duration_seconds=30, title="The Problem", content="Healthcare faces many challenges."),
            ScriptSection(timestamp="0:30", duration_seconds=120, title="How AI Helps", content="AI is transforming diagnostics."),
            ScriptSection(timestamp="2:30", duration_seconds=60, title="Real Examples", content="Hospitals using AI today."),
        ],
        conclusion="AI will transform healthcare forever.",
        call_to_action="Like and subscribe for more tech content!",
        full_script="Full video script content here...",
        estimated_duration_seconds=210,
        word_count=350,
        target_audience="tech enthusiasts",
        tone="professional",
        key_points=["AI improves diagnosis", "Reduces errors", "Saves costs"]
    )


@pytest.fixture
def sample_youtube_metadata():
    """Sample YouTube metadata for testing."""
    from app.models.youtube import YouTubeMetadata
    return YouTubeMetadata(
        title="How AI is Revolutionizing Healthcare",
        description="In this video, we explore how AI is transforming healthcare.\n\n0:00 - The Problem\n0:30 - How AI Helps\n2:30 - Real Examples",
        tags=["AI", "healthcare", "artificial intelligence", "medical tech", "future of medicine"],
        category_id=27
    )


@pytest.fixture
def sample_thumbnail_design():
    """Sample thumbnail design for testing."""
    from app.models.youtube import ThumbnailDesign
    return ThumbnailDesign(
        video_title="How AI is Revolutionizing Healthcare",
        concept_description="A split screen showing a doctor on one side and an AI interface on the other, with a surprised expression.",
        composition_guide="Left third: doctor's face with surprised expression. Right third: AI diagnostic screen. Center: bold text.",
        color_scheme=["#007AFF", "#FF3B30", "#FFFFFF", "#000000"],
        text_overlay="AI DOCTOR?",
        style_notes="High contrast, modern tech aesthetic."
    )