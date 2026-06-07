import pytest
from unittest.mock import AsyncMock, patch
from app.agents.thumbnail_agent import ThumbnailAgent
from app.models.content import AgentType


class TestThumbnailAgent:
    @pytest.fixture
    def agent(self):
        return ThumbnailAgent()

    @pytest.mark.asyncio
    async def test_initialization(self, agent):
        assert agent.agent_type == AgentType.VISUAL

    @pytest.mark.asyncio
    async def test_validate_input(self, agent):
        assert await agent.validate_input({"topic": "AI"}) is True
        assert await agent.validate_input({}) is False

    def test_color_scheme_by_niche(self, agent):
        palette = agent._get_color_scheme("tech", [])
        assert len(palette) == 4
        assert "#007AFF" in palette

        palette = agent._get_color_scheme("gaming", [])
        assert "#FF3B30" in palette

        palette = agent._get_color_scheme("unknown_niche", [])
        assert len(palette) == 4

    def test_color_scheme_with_emotions(self, agent):
        palette = agent._get_color_scheme("tech", ["surprise"])
        assert len(palette) == 4
        assert all(c in palette for c in ["#007AFF", "#FF3B30"])

        palette = agent._get_color_scheme("tech", ["urgency"])
        assert palette[0] == "#FF3B30"
        assert palette[1] == "#FF9500"

    @pytest.mark.asyncio
    async def test_execute_fallback(self, agent):
        with patch.object(agent, '_generate_concept', new=AsyncMock(return_value="Test concept")):
            with patch.object(agent, '_generate_composition_guide', new=AsyncMock(return_value="Test composition")):
                with patch.object(agent, '_generate_text_overlay', new=AsyncMock(return_value="WATCH THIS")):
                    with patch.object(agent, '_generate_ai_prompt', new=AsyncMock(return_value="AI prompt")):
                        with patch.object(agent, '_analyze_key_emotions', new=AsyncMock(return_value=["curiosity"])):
                            result = await agent.execute({
                                "topic": "test",
                                "title": "Test Video",
                                "script": {"hook": "Test hook"},
                                "research_data": {},
                                "niche": "tech"
                            })
                            assert result["status"] == "success"
                            assert result["thumbnail"] is not None
                            assert result["thumbnail"]["video_title"] == "Test Video"
                            assert result["thumbnail"]["text_overlay"] == "WATCH THIS"
