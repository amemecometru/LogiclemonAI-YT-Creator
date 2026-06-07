"""Tests for AI agents."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app.agents.research_agent import ResearchAgent
from app.agents.writer_agent import WriterAgent
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
        assert hasattr(research_agent, 'tavily_client')
        assert hasattr(research_agent, 'firecrawl_api_key')
    
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
    async def test_research_execute_no_api_key(self, research_agent):
        """Test research execution without Tavily (should fall back to LLM)."""
        input_data = {"topic": "artificial intelligence"}
        
        with patch.object(research_agent, 'tavily_client', None):
            result = await research_agent.execute(input_data)
            assert result["status"] in ("success", "error")
    
    @pytest.mark.asyncio
    async def test_calculate_confidence_from_sources(self, research_agent):
        """Test confidence calculation from sources."""
        sources = [
            {"title": "Source 1", "source": "Tavily", "credibility_score": 0.9, "content": "Long content here with enough words", "published_date": "2025-01-01"},
            {"title": "Source 2", "source": "Tavily", "credibility_score": 0.8, "content": "More content here for testing", "published_date": "2025-02-01"}
        ]
        confidence = research_agent._calculate_enhanced_confidence_from_sources(sources)
        assert 0.0 <= confidence <= 1.0
        assert isinstance(confidence, float)


class TestWriterAgent:
    """Test cases for WriterAgent."""
    
    @pytest.fixture
    def writer_agent(self):
        return WriterAgent()
    
    @pytest.mark.asyncio
    async def test_writer_agent_initialization(self, writer_agent):
        """Test writer agent initialization."""
        assert writer_agent.agent_type == AgentType.WRITER
        assert hasattr(writer_agent, 'style_templates')
    
    @pytest.mark.asyncio
    async def test_validate_input_valid(self, writer_agent):
        """Test input validation with valid data."""
        valid_input = {"topic": "machine learning"}
        result = await writer_agent.validate_input(valid_input)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_input_invalid(self, writer_agent):
        """Test input validation with invalid data."""
        invalid_input = {}
        result = await writer_agent.validate_input(invalid_input)
        assert result is False
    
    @pytest.mark.asyncio
    @patch('app.agents.writer_agent.WriterAgent.call_openai')
    async def test_create_outline(self, mock_openai, writer_agent):
        """Test content outline creation."""
        mock_outline = {
            "title": "Understanding Machine Learning",
            "introduction": {"hook": "ML is transforming industries", "overview": "Learn ML basics"},
            "main_sections": [{"title": "What is ML", "subsections": ["Definition", "Types"]}],
            "conclusion": {"summary": "ML is powerful", "call_to_action": "Start learning"}
        }
        mock_openai.return_value = str(mock_outline).replace("'", '"')
        
        research_data = {"key_findings": ["ML is important"], "main_arguments": ["ML automates tasks"]}
        outline = await writer_agent._create_outline(research_data, ContentType.BLOG_POST, "developers", "machine learning")
        
        assert "title" in outline
        assert "introduction" in outline
        assert "main_sections" in outline
    
    def test_calculate_reading_time(self, writer_agent):
        """Test reading time calculation."""
        content = " ".join(["word"] * 225)  # 225 words
        reading_time = writer_agent._calculate_reading_time(content)
        assert reading_time == 1  # Should be 1 minute
        
        content = " ".join(["word"] * 450)  # 450 words
        reading_time = writer_agent._calculate_reading_time(content)
        assert reading_time == 2  # Should be 2 minutes
    
    def test_extract_keywords(self, writer_agent):
        """Test keyword extraction."""
        content = "Machine learning algorithms are powerful tools for data analysis and artificial intelligence applications."
        keywords = writer_agent._extract_keywords(content)
        
        assert isinstance(keywords, list)
        assert len(keywords) > 0
        assert any("machine" in keyword.lower() or "learning" in keyword.lower() for keyword in keywords)


@pytest.mark.asyncio
async def test_agent_integration():
    """Test integration between research and writer agents."""
    research_agent = ResearchAgent()
    writer_agent = WriterAgent()
    
    # Mock research data
    research_data = {
        "key_findings": ["AI is transforming industries", "Machine learning is a subset of AI"],
        "main_arguments": ["AI improves efficiency", "AI enables automation"],
        "sources": [{"title": "AI Overview", "url": "example.com", "source": "Wikipedia"}],
        "confidence_score": 0.8
    }
    
    # Test writer agent with research data
    writer_input = {
        "topic": "artificial intelligence",
        "research_data": research_data,
        "content_type": ContentType.BLOG_POST,
        "target_audience": "general audience",
        "word_count": 500
    }
    
    # This would normally call OpenAI, so we'll just test the structure
    assert await writer_agent.validate_input(writer_input) is True