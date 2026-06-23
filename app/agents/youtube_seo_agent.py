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
            model = input_data.get("model")
            byok_key = input_data.get("byok_key")

            title_pkg = await self._generate_title_package(title, topic, research_data, target_audience, model=model, byok_key=byok_key)
            optimized_title = title_pkg.get("optimized_title", title)
            title_variants = title_pkg.get("title_variants", [title[:60]])

            meta_pkg = await self._generate_metadata_package(topic, script, research_data, target_audience, channel_config, model=model, byok_key=byok_key)
            tags = meta_pkg.get("tags", [topic])
            description = meta_pkg.get("description", "")
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
                "title_variants": title_variants
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

    async def _generate_title_package(self, current_title: str, topic: str,
                                       research_data: Dict[str, Any], audience: str,
                                       model: str | None = None, byok_key: str | None = None) -> Dict[str, Any]:
        findings = research_data.get("key_findings", [])
        findings_text = "\n".join(f"- {f}" for f in findings[:3])

        prompt = f"""Optimize this YouTube title and generate 5 title variants for a video about "{topic}" for {audience}.

Current title: "{current_title}"
Research context:
{findings_text}

Optimized title rules:
- 30-60 characters
- Include a power word or number
- Create curiosity gap
- Start with a hook pattern

Title variants rules:
- Each 30-60 characters
- Different angle/approach
- Clickable and SEO-friendly

Return as JSON:
{{
    "optimized_title": "...",
    "title_variants": ["variant 1", "variant 2", "variant 3", "variant 4", "variant 5"]
}}"""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, model=model, byok_key=byok_key, max_tokens=500, temperature=0.7)
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            data = json.loads(response.strip())
            if not isinstance(data, dict):
                raise ValueError("LLM returned non-object JSON")
            opt = data.get("optimized_title", "").strip().strip('"\'')
            if not (20 <= len(opt) <= 100):
                opt = current_title[:60]
            return {"optimized_title": opt or current_title[:60], "title_variants": data.get("title_variants", [current_title[:60]])[:5]}
        except Exception:
            return {"optimized_title": (current_title or topic)[:60], "title_variants": [current_title[:60]]}

    async def _generate_metadata_package(self, topic: str, script: Dict[str, Any],
                                          research_data: Dict[str, Any], audience: str,
                                          channel_config: Dict[str, Any],
                                          model: str | None = None, byok_key: str | None = None) -> Dict[str, Any]:
        sections = script.get("sections", [])
        hook = script.get("hook", "")
        findings = research_data.get("key_findings", [])
        findings_text = "\n".join(f"- {f}" for f in findings[:3])
        section_list = "\n".join(f"- {s.get('title', '')}" for s in sections[:5])
        brand_keywords = channel_config.get("brand_keywords", []) if channel_config else []

        prompt = f"""Generate YouTube tags and a video description for "{topic}" targeted at {audience}.

Hook: {hook}
Sections: {section_list}
Research context:
{findings_text}
Brand keywords: {', '.join(brand_keywords) if brand_keywords else 'None'}

Tags rules:
- 15-20 tags, mix of broad and specific
- Include common misspellings and variations
- Return as JSON array of strings

Description rules:
- First 2 lines must hook the viewer (shows in search results)
- 150-300 words, paragraph breaks
- Include relevant hashtags at the end
- Include: "📩 Business inquiries: [email]" placeholder
- Include a resources/links section placeholder

Return as JSON:
{{
    "tags": ["tag1", "tag2", ...],
    "description": "..."
}}"""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, model=model, byok_key=byok_key, max_tokens=800, temperature=0.7)
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            data = json.loads(response.strip())
            if not isinstance(data, dict):
                raise ValueError("LLM returned non-object JSON")
            tags = data.get("tags", [topic])
            all_tags = list(set(tags + brand_keywords))[:20]
            desc = data.get("description", "")
            sources = research_data.get("sources", [])
            if sources:
                desc += "\n\n📚 Sources:\n"
                for s in sources[:5]:
                    desc += f"- {s.get('title', 'Source')}: {s.get('url', '')}\n"
            desc += "\n\n#YouTube #" + topic.replace(" ", "")
            return {"tags": all_tags, "description": desc}
        except Exception:
            return {
                "tags": [topic] + topic.split() + brand_keywords,
                "description": (f"In this video, we explore {topic}. "
                               f"You'll learn about the key concepts and practical applications.\n\n"
                               f"📩 Business inquiries: your@email.com\n\n"
                               f"#YouTube #{topic.replace(' ', '')}")
            }

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
