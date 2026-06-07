import pytest
from unittest.mock import AsyncMock, patch
from app.agents.youtube_seo_agent import YouTubeSEOAgent
from app.models.content import AgentType


class TestYouTubeSEOAgent:
    @pytest.fixture
    def agent(self):
        return YouTubeSEOAgent()

    @pytest.mark.asyncio
    async def test_initialization(self, agent):
        assert agent.agent_type == AgentType.SEO

    @pytest.mark.asyncio
    async def test_validate_input(self, agent):
        assert await agent.validate_input({"topic": "AI"}) is True
        assert await agent.validate_input({}) is False

    def test_generate_timestamps(self, agent):
        script = {
            "sections": [
                {"timestamp": "0:00", "title": "Intro"},
                {"timestamp": "1:30", "title": "Main Content"},
                {"timestamp": "5:00", "title": "Conclusion"}
            ]
        }
        result = agent._generate_timestamps(script)
        assert "0:00" in result
        assert "Intro" in result
        assert "1:30" in result
        assert "Main Content" in result

    def test_generate_timestamps_empty(self, agent):
        assert agent._generate_timestamps({}) == ""
        assert agent._generate_timestamps({"sections": []}) == ""

    @pytest.mark.asyncio
    async def test_execute_fallback(self, agent):
        result = await agent.execute({
            "topic": "test topic",
            "script": {"sections": [], "title": "Test"},
            "research_data": {},
            "target_audience": "general"
        })
        assert result["status"] == "success"
        assert result["metadata"] is not None
        assert result["metadata"]["title"]
