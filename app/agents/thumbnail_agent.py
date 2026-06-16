import urllib.parse
import httpx
from typing import Dict, Any, List, Optional
from app.agents.base_agent import BaseAgent
from app.models.content import AgentType, ContentStatus
from app.models.youtube import ThumbnailDesign


class ThumbnailAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.VISUAL)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        self.update_status(ContentStatus.PROCESSING)

        try:
            if not await self.validate_input(input_data):
                raise ValueError("Invalid input data for thumbnail agent")

            topic = input_data.get("topic", "")
            title = input_data.get("title", topic)
            script = input_data.get("script", {})
            research_data = input_data.get("research_data", {})
            niche = input_data.get("niche", "general")

            hook = script.get("hook", "")
            key_emotions = await self._analyze_key_emotions(topic, hook, research_data)
            concept = await self._generate_concept(topic, title, key_emotions, niche)
            composition = await self._generate_composition_guide(concept)
            color_scheme = self._get_color_scheme(niche, key_emotions)
            text_overlay = await self._generate_text_overlay(title, topic)
            generation_prompt = await self._generate_ai_prompt(concept, composition, color_scheme, text_overlay)
            thumbnail_url = await self._render_thumbnail(generation_prompt)

            thumbnail = ThumbnailDesign(
                video_title=title,
                concept_description=concept,
                composition_guide=composition,
                color_scheme=color_scheme,
                text_overlay=text_overlay,
                ai_generation_prompt=generation_prompt,
                thumbnail_url=thumbnail_url,
                style_notes=f"Design for {niche} niche. Focus on high contrast, readable text, and emotional trigger."
            )

            self.update_status(ContentStatus.COMPLETED)

            return {
                "status": "success",
                "thumbnail": thumbnail.model_dump()
            }

        except Exception as e:
            self.update_status(ContentStatus.FAILED)
            return {
                "status": "error",
                "message": str(e),
                "thumbnail": None
            }

    async def _render_thumbnail(self, prompt: str) -> str:
        """Render a real 1280x720 thumbnail from the prompt via Pollinations (free, no key).
        Returns an image URL (best-effort; empty string on failure)."""
        try:
            encoded = urllib.parse.quote((prompt or "")[:400], safe="")
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&nologo=true&nofeed=true"
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.head(url)
                if resp.status_code < 500:
                    return url
        except Exception as e:
            print(f"Thumbnail render failed: {e}")
        return ""

    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        return bool(input_data.get("topic"))

    async def _analyze_key_emotions(self, topic: str, hook: str,
                                     research_data: Dict[str, Any]) -> List[str]:
        findings = research_data.get("key_findings", [])
        findings_text = "\n".join(f"- {f}" for f in findings[:3])

        prompt = f"""Analyze what emotions this YouTube video should trigger in the thumbnail.

Topic: {topic}
Hook: {hook}
Content: {findings_text}

Return 3-5 emotion keywords that the thumbnail should convey.
Examples: curiosity, urgency, surprise, awe, fear of missing out, controversy, inspiration

Return as JSON array of strings ONLY."""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, max_tokens=150, temperature=0.5)
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            emotions = json.loads(response.strip())
            return emotions[:5]
        except Exception:
            return ["curiosity", "surprise"]

    async def _generate_concept(self, topic: str, title: str,
                                 emotions: List[str], niche: str) -> str:
        emotions_text = ", ".join(emotions)

        prompt = f"""Create a YouTube thumbnail concept for a video titled "{title}" about {topic}.

Niche: {niche}
Emotions to convey: {emotions_text}

Describe in 3-4 sentences:
1. Main focal point (what's in the center)
2. Background setting
3. People/expressions (if any)
4. Visual hook element

Focus on what would make someone stop scrolling and click."""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, max_tokens=300, temperature=0.8)
            return response.strip()
        except Exception:
            return f"A bold image representing {topic} with a surprised expression and contrasting colors to grab attention."

    async def _generate_composition_guide(self, concept: str) -> str:
        prompt = f"""Convert this thumbnail concept into a specific visual composition guide:

Concept: {concept}

Provide a composition guide covering:
1. Layout (rule of thirds, center focus, etc.)
2. Focal point position
3. Text placement
4. Lighting direction
5. Depth of field

Keep it practical and specific, 3-5 sentences."""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, max_tokens=300, temperature=0.5)
            return response.strip()
        except Exception:
            return ("Center-focused composition with subject on left third, "
                    "text overlay on right third. High contrast lighting. "
                    "Shallow depth of field to emphasize subject.")

    def _get_color_scheme(self, niche: str, emotions: List[str]) -> List[str]:
        niche_palettes = {
            "tech": ["#007AFF", "#FF3B30", "#FFFFFF", "#000000"],
            "education": ["#34C759", "#007AFF", "#FFFFFF", "#5856D6"],
            "entertainment": ["#FF9500", "#FF3B30", "#FF2D55", "#FFFFFF"],
            "gaming": ["#FF3B30", "#007AFF", "#FF9500", "#000000"],
            "business": ["#007AFF", "#34C759", "#1C1C1E", "#FFFFFF"],
            "lifestyle": ["#FF2D55", "#FF9500", "#AF52DE", "#FFFFFF"],
            "health": ["#34C759", "#007AFF", "#FFFFFF", "#1C1C1E"],
        }
        palette = niche_palettes.get(niche.lower(), ["#FF3B30", "#007AFF", "#FFFFFF", "#000000"])

        if "surprise" in emotions:
            palette = [palette[1], palette[0]] + palette[2:]
        if "urgency" in emotions:
            palette = ["#FF3B30", "#FF9500"] + palette[2:]

        return palette[:4]

    async def _generate_text_overlay(self, title: str, topic: str) -> str:
        prompt = f"""Generate a short, punchy text overlay for a YouTube thumbnail.

Video title: {title}
Topic: {topic}

Rules:
- MAXIMUM 3 words
- Large, bold, readable font
- Creates curiosity or urgency
- Examples: "YOU'RE WRONG", "MIND BLOWN", "THIS CHANGES EVERYTHING", "GAME OVER"

Return ONLY the text string, no quotes."""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, max_tokens=50, temperature=0.8)
            text = response.strip().strip('"\'')
            words = text.split()
            return " ".join(words[:3]).upper()
        except Exception:
            return topic.split()[0].upper() if topic.split() else "WATCH THIS"

    async def _generate_ai_prompt(self, concept: str, composition: str,
                                   color_scheme: List[str], text: str) -> str:
        colors = ", ".join(color_scheme)
        return (f"Create a YouTube thumbnail. Concept: {concept} "
                f"Composition: {composition} "
                f"Color scheme: {colors} "
                f"Text overlay: '{text}' in bold white font with black stroke. "
                f"Style: photorealistic, high contrast, 1280x720.")


import json
