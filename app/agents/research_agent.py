import json
import asyncio
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.agents.base_agent import BaseAgent
from app.models.content import AgentType, ResearchData, ContentStatus
from app.config import settings


class ResearchAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.RESEARCH)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        self.update_status(ContentStatus.PROCESSING)

        try:
            if not await self.validate_input(input_data):
                raise ValueError("Invalid input data for research agent")

            topic = input_data.get("topic", "")
            max_results = input_data.get("max_results", 10)
            include_domains = input_data.get("include_domains", [])
            exclude_domains = input_data.get("exclude_domains", [])

            print(f"Researching: '{topic}'")

            if settings.cloudflare_research_url:
                results = await self._cloudflare_research(topic, max_results)
                if results:
                    structured = await self._structure_enhanced_findings(results, topic)
                    self.update_status(ContentStatus.COMPLETED)
                    return {
                        "status": "success",
                        "research_data": structured,
                        "confidence_score": self._calculate_enhanced_confidence(structured),
                        "sources_found": len(results),
                        "research_method": "cloudflare"
                    }

            print("Using LLM-based research fallback")
            structured_research = await self._llm_research(topic)
            self.update_status(ContentStatus.COMPLETED)
            return {
                "status": "success",
                "research_data": structured_research,
                "confidence_score": structured_research.get("confidence_score", 0.6),
                "sources_found": 0,
                "research_method": "llm"
            }

        except Exception as e:
            self.update_status(ContentStatus.FAILED)
            print(f"Research failed: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "research_data": ResearchData().model_dump()
            }

    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        required_fields = ["topic"]
        return all(field in input_data and input_data[field] for field in required_fields)

    async def _cloudflare_research(self, topic: str, max_results: int = 10) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = {"Content-Type": "application/json"}
                if settings.cloudflare_api_token:
                    headers["Authorization"] = f"Bearer {settings.cloudflare_api_token}"

                resp = await client.post(
                    settings.cloudflare_research_url,
                    headers=headers,
                    json={"topic": topic, "max_results": max_results}
                )

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "success":
                        return data.get("results", [])

                print(f"Cloudflare research error: {resp.status_code}")
                return []

        except Exception as e:
            print(f"Cloudflare research request failed: {e}")
            return []

    async def _llm_research(self, topic: str) -> Dict[str, Any]:
        prompt = f"""You are a research assistant. Provide comprehensive research about "{topic}".

Return a JSON object with this exact structure:
{{
    "key_findings": ["finding 1", "finding 2", "finding 3", "finding 4", "finding 5"],
    "main_arguments": ["argument 1", "argument 2", "argument 3"],
    "statistics": [
        {{"statistic": "description", "value": "number/percentage", "source": "source name"}}
    ],
    "expert_opinions": [
        {{"opinion": "expert view", "expert": "expert name", "source": "publication"}}
    ],
    "recent_developments": ["development 1", "development 2"],
    "practical_applications": ["application 1", "application 2"],
    "challenges_limitations": ["challenge 1", "challenge 2"]
}}

Base your research on well-known facts and common knowledge about this topic.
Include specific statistics, examples, and real-world applications.
Return ONLY valid JSON."""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, max_tokens=2000)
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            data = json.loads(response.strip())

            return {
                "key_findings": data.get("key_findings", [f"Key insight about {topic}"]),
                "main_arguments": data.get("main_arguments", []),
                "sources": [{"title": f"{topic} - Research Summary", "url": "", "source": "AI Research", "credibility_score": 0.7}],
                "statistics": data.get("statistics", []),
                "expert_opinions": data.get("expert_opinions", []),
                "confidence_score": 0.6,
                "recent_developments": data.get("recent_developments", []),
                "practical_applications": data.get("practical_applications", []),
                "challenges_limitations": data.get("challenges_limitations", []),
                "source_diversity": 1,
                "total_sources": 1,
                "avg_credibility": 0.7,
                "has_recent_content": False
            }
        except Exception as e:
            print(f"LLM research failed: {e}")
            return {
                "key_findings": [f"{topic} is an important topic with many applications"],
                "main_arguments": [],
                "sources": [],
                "statistics": [],
                "expert_opinions": [],
                "confidence_score": 0.5,
                "recent_developments": [],
                "practical_applications": [],
                "challenges_limitations": [],
                "source_diversity": 0,
                "total_sources": 0,
                "avg_credibility": 0.5,
                "has_recent_content": False
            }

    async def _structure_enhanced_findings(self, sources: List[Dict[str, Any]], topic: str) -> Dict[str, Any]:
        if not sources:
            return ResearchData().model_dump()

        source_summaries = []
        for i, source in enumerate(sources[:8], 1):
            summary = f"""
Source {i} (Credibility: {source.get('credibility_score', 0.5)})
Title: {source.get('title', 'No title')}
URL: {source.get('url', 'No URL')}
Content: {source.get('content', '')[:600]}...
"""
            source_summaries.append(summary)

        combined_content = "\n".join(source_summaries)

        prompt = f"""
        Analyze the following comprehensive research about "{topic}" and provide detailed structured analysis.

        Research Sources:
        {combined_content}

        Provide analysis in this JSON format:
        {{
            "key_findings": ["finding 1", "finding 2", "finding 3", "finding 4", "finding 5"],
            "main_arguments": ["argument 1", "argument 2", "argument 3"],
            "statistics": [
                {{"statistic": "description", "value": "number/percentage", "source": "source name", "reliability": "high/medium/low"}}
            ],
            "expert_opinions": [
                {{"opinion": "expert view", "expert": "expert name or source", "source": "publication/platform"}}
            ],
            "recent_developments": ["development 1", "development 2"],
            "practical_applications": ["application 1", "application 2"],
            "challenges_limitations": ["challenge 1", "challenge 2"]
        }}

        Focus on:
        1. Factual accuracy and source credibility
        2. Current and relevant information
        3. Diverse perspectives and viewpoints
        4. Actionable insights
        5. Clear distinction between facts and opinions

        Return only valid JSON.
        """

        messages = [{"role": "user", "content": prompt}]

        try:
            response = await self.call_openai(messages, max_tokens=2000)

            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            structured_data = json.loads(response)

            research_data = ResearchData(
                key_findings=structured_data.get("key_findings", []),
                main_arguments=structured_data.get("main_arguments", []),
                sources=[{
                    "title": source.get("title", ""),
                    "url": source.get("url", ""),
                    "source": "Cloudflare Research",
                    "credibility_score": source.get("credibility_score", 0.5),
                } for source in sources],
                statistics=structured_data.get("statistics", []),
                expert_opinions=structured_data.get("expert_opinions", []),
                confidence_score=self._calculate_enhanced_confidence_from_sources(sources)
            )

            enhanced_data = research_data.model_dump()
            enhanced_data.update({
                "recent_developments": structured_data.get("recent_developments", []),
                "practical_applications": structured_data.get("practical_applications", []),
                "challenges_limitations": structured_data.get("challenges_limitations", []),
                "source_diversity": len(set(s.get("source", "") for s in sources)),
                "total_sources": len(sources),
                "avg_credibility": sum(s.get("credibility_score", 0.5) for s in sources) / len(sources) if sources else 0,
                "has_recent_content": True
            })

            return enhanced_data

        except (json.JSONDecodeError, Exception) as e:
            print(f"Error structuring findings: {e}")
            return ResearchData(
                key_findings=[f"Comprehensive research conducted on {topic}"],
                sources=[{
                    "title": source.get("title", ""),
                    "url": source.get("url", ""),
                    "source": "Cloudflare Research",
                    "credibility_score": source.get("credibility_score", 0.5)
                } for source in sources],
                confidence_score=0.7
            ).model_dump()

    def _calculate_enhanced_confidence(self, research_data: Dict[str, Any]) -> float:
        sources = research_data.get("sources", [])
        key_findings = research_data.get("key_findings", [])

        if not sources:
            return 0.1

        source_score = min(len(sources) / 8.0, 1.0)
        findings_score = min(len(key_findings) / 6.0, 1.0)
        source_diversity = research_data.get("source_diversity", 1) / 4.0
        source_diversity = min(source_diversity, 1.0)
        avg_credibility = research_data.get("avg_credibility", 0.5)
        recent_bonus = 0.1 if research_data.get("has_recent_content", False) else 0
        enhanced_bonus = 0.05 if research_data.get("recent_developments") else 0

        confidence = (
            source_score * 0.25 +
            findings_score * 0.25 +
            source_diversity * 0.2 +
            avg_credibility * 0.3
        ) + recent_bonus + enhanced_bonus

        return min(confidence, 1.0)

    def _calculate_enhanced_confidence_from_sources(self, sources: List[Dict[str, Any]]) -> float:
        if not sources:
            return 0.1

        avg_credibility = sum(s.get("credibility_score", 0.5) for s in sources) / len(sources)
        unique_sources = len(set(s.get("source", "") for s in sources))
        source_diversity = min(unique_sources / 4.0, 1.0)
        content_quality = sum(1 for s in sources if len(s.get("content", "")) > 100) / len(sources)

        confidence = (
            avg_credibility * 0.4 +
            source_diversity * 0.3 +
            content_quality * 0.2 +
            0.8 * 0.1
        )

        return min(confidence, 1.0)
