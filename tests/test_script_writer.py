import pytest
from unittest.mock import AsyncMock, patch
from app.agents.script_writer_agent import ScriptWriterAgent
from app.models.content import AgentType
from app.models.youtube import VideoLength


class TestScriptWriterAgent:
    @pytest.fixture
    def agent(self):
        return ScriptWriterAgent()

    @pytest.mark.asyncio
    async def test_initialization(self, agent):
        assert agent.agent_type == AgentType.WRITER
        assert hasattr(agent, 'intro_durations')
        assert hasattr(agent, 'section_durations')

    @pytest.mark.asyncio
    async def test_validate_input_valid(self, agent):
        assert await agent.validate_input({"topic": "AI"}) is True

    @pytest.mark.asyncio
    async def test_validate_input_invalid(self, agent):
        assert await agent.validate_input({}) is False
        assert await agent.validate_input({"topic": ""}) is False

    @pytest.mark.asyncio
    async def test_target_duration(self, agent):
        assert agent._get_target_duration(VideoLength.SHORT) == 60
        assert agent._get_target_duration(VideoLength.MEDIUM) == 480
        assert agent._get_target_duration(VideoLength.LONG) == 1200

    def test_fallback_sections(self, agent):
        sections = agent._generate_fallback_sections("AI", 4, 60)
        assert len(sections) == 4
        for s in sections:
            assert s.timestamp
            assert s.duration_seconds > 0
            assert s.title
            assert s.content
            assert s.visual_cue

    @pytest.mark.asyncio
    async def test_generate_title_fallback(self, agent):
        title = await agent._generate_title("test", {}, "general")
        assert isinstance(title, str)
        assert len(title) > 0

    @pytest.mark.asyncio
    async def test_execute_no_research(self, agent):
        with patch.object(agent, '_generate_title', new=AsyncMock(return_value="Test Title")):
            with patch.object(agent, '_generate_hook', new=AsyncMock(return_value="Test hook")):
                with patch.object(agent, '_generate_sections', return_value=agent._generate_fallback_sections("test", 3, 60)):
                    with patch.object(agent, '_generate_conclusion', new=AsyncMock(return_value="Conclusion")):
                        with patch.object(agent, '_generate_cta', new=AsyncMock(return_value="CTA")):
                            result = await agent.execute({
                                "topic": "test",
                                "research_data": {},
                                "video_length": "medium"
                            })
                            assert result["status"] == "success"
                            assert result["script"] is not None
                            assert result["script"]["title"] == "Test Title"
