import json
from typing import Dict, Any, List
from app.agents.base_agent import BaseAgent
from app.models.content import AgentType, ContentStatus
from app.models.youtube import YouTubeMetadata


class YouTubeSEOAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.SEO)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        self.update_status(ContentStatus.PROCESSING)

        try:
            if not await self.validate_input(input_data):
                raise ValueError("Invalid input data for SEO agent")

            topic = input_data.get("topic", "")
            script = input_data.get("script", {})
            research_data = input_data.get("research_data", {})
            target_audience = input_data.get("target_audience", "general audience")
            title = script.get("title", topic)
            channel_config = input_data.get("channel_config", {})

            optimized_title = await self._optimize_title(title, topic, research_data, target_audience)
            tags = await self._generate_tags(topic, research_data, channel_config)
            description = await self._generate_description(topic, script, research_data, target_audience)
            timestamps = self._generate_timestamps(script)

            full_description = description + "\n\n" + timestamps if timestamps else description

            category_id = channel_config.get("default_category_id", 22) if channel_config else 22

            metadata = YouTubeMetadata(
                title=optimized_title,
                description=full_description,
                tags=tags,
                category_id=category_id,
                made_for_kids=False
            )

            self.update_status(ContentStatus.COMPLETED)

            return {
                "status": "success",
                "metadata": metadata.model_dump(),
                "title_variants": await self._generate_title_variants(title, topic, target_audience)
            }

        except Exception as e:
            self.update_status(ContentStatus.FAILED)
            return {
                "status": "error",
                "message": str(e),
                "metadata": None,
                "title_variants": []
            }

    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        return bool(input_data.get("topic"))

    async def _optimize_title(self, current_title: str, topic: str,
                                research_data: Dict[str, Any], audience: str) -> str:
        findings = research_data.get("key_findings", [])
        findings_text = "\n".join(f"- {f}" for f in findings[:3])

        prompt = f"""Optimize this YouTube title for CTR and SEO:

Current title: "{current_title}"
Topic: {topic}
Target audience: {audience}

Research context:
{findings_text}

Rules:
- 30-60 characters
- Include a power word or number
- Create curiosity gap
- Start with a hook pattern

Return ONLY the optimized title string, no quotes."""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, max_tokens=100, temperature=0.7)
            title = response.strip().strip('"\'')
            if 20 <= len(title) <= 100:
                return title
            return current_title[:60] if current_title else topic[:60]
        except Exception:
            return (current_title or topic)[:60]

    async def _generate_title_variants(self, current_title: str, topic: str,
                                        audience: str) -> List[str]:
        prompt = f"""Generate 5 YouTube title variants for a video about "{topic}" for {audience}.

Current title: "{current_title}"

Each title must:
- Be 30-60 characters
- Be clickable and SEO-friendly
- Be different angle/approach

Return as JSON array of strings only.

Example: ["Title 1", "Title 2", "Title 3", "Title 4", "Title 5"]"""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, max_tokens=400, temperature=0.8)
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            return json.loads(response.strip())[:5]
        except Exception:
            return [current_title[:60]] if current_title else [f"{topic} - Complete Guide"]

    async def _generate_tags(self, topic: str, research_data: Dict[str, Any],
                              channel_config: Dict[str, Any]) -> List[str]:
        brand_keywords = channel_config.get("brand_keywords", []) if channel_config else []
        findings = research_data.get("key_findings", [])
        findings_text = "\n".join(f"- {f}" for f in findings[:3])

        prompt = f"""Generate 15-20 YouTube tags for a video about "{topic}".

Research context:
{findings_text}

Brand keywords: {', '.join(brand_keywords) if brand_keywords else 'None'}

Rules:
- Mix of broad and specific tags
- Include common misspellings and variations
- Include related topics
- Each tag should be a single word or short phrase
- Return as JSON array of strings ONLY"""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, max_tokens=500, temperature=0.5)
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            tags = json.loads(response.strip())
            all_tags = list(set(tags + brand_keywords))
            return all_tags[:20]
        except Exception:
            return [topic] + topic.split() + brand_keywords

    async def _generate_description(self, topic: str, script: Dict[str, Any],
                                     research_data: Dict[str, Any], audience: str) -> str:
        sections = script.get("sections", [])
        hook = script.get("hook", "")
        key_findings = research_data.get("key_findings", [])
        sources = research_data.get("sources", [])

        section_list = "\n".join(f"- {s.get('title', '')}" for s in sections[:5])

        prompt = f"""Write a YouTube video description for "{topic}" targeted at {audience}.

Hook: {hook}
Sections covered: {section_list}

Requirements:
- First 2 lines must hook the viewer (this shows in search results)
- Include what the viewer will learn
- 150-300 words
- Use paragraph breaks for readability
- Include relevant hashtags at the end
- Include: "📩 Business inquiries: [email]" placeholder
- Include a resources/links section placeholder

Write the full description."""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, max_tokens=600, temperature=0.7)
            desc = response.strip()
            if sources:
                desc += "\n\n📚 Sources:\n"
                for s in sources[:5]:
                    title = s.get("title", "Source")
                    url = s.get("url", "")
                    desc += f"- {title}: {url}\n"
            desc += "\n\n#YouTube #" + topic.replace(" ", "")

            hashtags = "#" + " #".join(topic.split()[:3])
            desc += f"\n\n{hashtags}"
            return desc
        except Exception:
            return (f"In this video, we explore {topic}. "
                    f"You'll learn about the key concepts and practical applications.\n\n"
                    f"📩 Business inquiries: your@email.com\n\n"
                    f"#YouTube #{topic.replace(' ', '')}")

    def _generate_timestamps(self, script: Dict[str, Any]) -> str:
        sections = script.get("sections", [])
        if not sections:
            return ""

        lines = []
        for sec in sections:
            ts = sec.get("timestamp", "0:00")
            title = sec.get("title", "Introduction")
            lines.append(f"{ts} - {title}")

        if lines:
            return "⏱ Timestamps:\n" + "\n".join(lines)
        return ""
