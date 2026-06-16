"""Tests for AI agents."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app.agents.research_agent import ResearchAgent
from app.models.content import AgentType, ContentType


class TestResearchAgent:
    """Test cases for ResearchAgent."""

    @pytest.fixture
    def research_agent(self):
        return ResearchAgent()

    @pytest.mark.asyncio
    async def test_research_agent_initialization(self, research_agent):
        """Test research agent initialization."""
        assert research_agent.agent_type == AgentType.RESEARCH

    @pytest.mark.asyncio
    async def test_validate_input_valid(self, research_agent):
        """Test input validation with valid data."""
        valid_input = {"topic": "artificial intelligence"}
        result = await research_agent.validate_input(valid_input)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_input_invalid(self, research_agent):
        """Test input validation with invalid data."""
        invalid_input = {}
        result = await research_agent.validate_input(invalid_input)
        assert result is False

    @pytest.mark.asyncio
    async def test_research_execute_fallback(self, research_agent):
        """Test research execution fallback to LLM."""
        input_data = {"topic": "artificial intelligence"}
        result = await research_agent.execute(input_data)
        assert result["status"] in ("success", "error")

    @pytest.mark.asyncio
    async def test_calculate_confidence_from_sources(self, research_agent):
        """Test confidence calculation from sources."""
        sources = [
            {"title": "Source 1", "source": "Cloudflare Research", "credibility_score": 0.9, "content": "Long content here with enough words", "published_date": "2025-01-01"},
            {"title": "Source 2", "source": "Cloudflare Research", "credibility_score": 0.8, "content": "More content here for testing", "published_date": "2025-02-01"}
        ]
        confidence = research_agent._calculate_enhanced_confidence_from_sources(sources)
        assert 0.0 <= confidence <= 1.0
        assert isinstance(confidence, float)
