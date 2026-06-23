import json
import base64
import time
import httpx
import hashlib
import os
import urllib.parse
from typing import Dict, Any, List, Optional
from app.agents.base_agent import BaseAgent
from app.models.content import AgentType, ContentStatus
from app.models.youtube import ThumbnailDesign
from app.config import settings


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
            model = input_data.get("model")
            byok_key = input_data.get("byok_key")

            hook = script.get("hook", "")
            key_emotions = await self._analyze_key_emotions(topic, hook, research_data, model=model, byok_key=byok_key)

            design_pkg = await self._generate_design_package(topic, title, key_emotions, niche, model=model, byok_key=byok_key)
            concept = design_pkg.get("concept", "")
            composition = design_pkg.get("composition", "")
            text_overlay = design_pkg.get("text_overlay", "")
            color_scheme = self._get_color_scheme(niche, key_emotions)
            generation_prompt = self._build_ai_prompt(concept, composition, color_scheme, text_overlay)

            thumbnail_data = await self._render_thumbnail(generation_prompt, title)

            thumbnail = ThumbnailDesign(
                video_title=title,
                concept_description=concept,
                composition_guide=composition,
                color_scheme=color_scheme,
                text_overlay=text_overlay,
                ai_generation_prompt=generation_prompt,
                thumbnail_url=thumbnail_data.get("url", ""),
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

    async def _render_thumbnail(self, prompt: str, title: str) -> Dict[str, Any]:
        image_data = await self._render_via_openrouter(prompt, title)
        if image_data:
            return image_data
        image_data = await self._render_via_pollinations(prompt, title)
        if image_data:
            return image_data
        return {"url": "", "format": ""}

    async def _render_via_openrouter(self, prompt: str, title: str) -> Optional[Dict[str, Any]]:
        if not settings.openai_api_key:
            return None
        models = [
            "google/gemini-2.5-flash-image",
        ]
        for model in models:
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(
                        f"{settings.openai_base_url or 'https://openrouter.ai/api/v1'}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {settings.openai_api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": [
                                {"type": "text", "text": f"Generate a YouTube thumbnail image. {prompt}"}
                            ]}],
                            "modalities": ["image", "text"],
                        },
                    )
                    if resp.status_code != 200:
                        err = resp.json().get("error", {}).get("message", resp.text)
                        print(f"OpenRouter image error ({model}): {err}")
                        continue

                    data = resp.json()
                    msg = data.get("choices", [{}])[0].get("message", {})

                    images = msg.get("images", [])
                    if images and isinstance(images, list):
                        url = images[0].get("image_url", {}).get("url", "")
                        if url:
                            return self._save_image(url, title)

                    content = msg.get("content", "")
                    if content:
                        import re
                        urls = re.findall(r'https?://[^\s)\']+', content)
                        if urls:
                            return self._save_image(urls[0], title)
                        if "data:image" in content:
                            return self._save_image(content.strip(), title)
            except Exception as e:
                print(f"OpenRouter render failed ({model}): {e}")
                continue
        return None

    async def _render_via_pollinations(self, prompt: str, title: str) -> Optional[Dict[str, Any]]:
        try:
            import urllib.parse
            safe_prompt = urllib.parse.quote(prompt[:400])
            url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1280&height=720&nofeed=true"
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code < 500:
                    import base64
                    img_b64 = base64.b64encode(resp.content).decode()
                    data_url = f"data:image/jpeg;base64,{img_b64}"
                    return self._save_image(data_url, title)
                return None
        except Exception as e:
            print(f"Pollinations render failed: {e}")
            return None

    def _save_image(self, data_url: str, title: str) -> Dict[str, Any]:
        import os, re
        thumb_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "output", "thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)

        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', title.strip())[:50]
        filename = f"{safe_name}_{int(time.time())}.png"
        filepath = os.path.join(thumb_dir, filename)

        if data_url.startswith("data:image"):
            import base64
            b64_data = data_url.split(",", 1)[1]
            img_bytes = base64.b64decode(b64_data)
            with open(filepath, "wb") as f:
                f.write(img_bytes)
        else:
            return {"url": data_url, "format": "image/png"}

        return {"url": filepath, "format": "image/png"}

    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        return bool(input_data.get("topic"))

    async def _analyze_key_emotions(self, topic: str, hook: str,
                                     research_data: Dict[str, Any],
                                     model: str | None = None, byok_key: str | None = None) -> List[str]:
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
            response = await self.call_openai(messages, model=model, byok_key=byok_key, max_tokens=150, temperature=0.5)
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            emotions = json.loads(response.strip())
            if not isinstance(emotions, list):
                raise ValueError("LLM returned non-list JSON")
            return emotions[:5]
        except Exception:
            return ["curiosity", "surprise"]

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

    async def _generate_design_package(self, topic: str, title: str,
                                       emotions: List[str], niche: str,
                                       model: str | None = None, byok_key: str | None = None) -> Dict[str, str]:
        emotions_text = ", ".join(emotions)

        prompt = f"""Create a complete YouTube thumbnail design for a video titled "{title}" about {topic}.

Niche: {niche}
Emotions to convey: {emotions_text}

Provide three things as JSON:

1. "concept": 3-4 sentence description of the thumbnail visual:
   - Main focal point
   - Background setting
   - People/expressions
   - Visual hook element

2. "composition": 3-5 sentence composition guide:
   - Layout (rule of thirds, center focus)
   - Focal point position
   - Text placement
   - Lighting direction
   - Depth of field

3. "text_overlay": MAX 3 words, punchy, creates curiosity or urgency

Return as JSON:
{{
    "concept": "...",
    "composition": "...",
    "text_overlay": "..."
}}"""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, model=model, byok_key=byok_key, max_tokens=600, temperature=0.7)
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            data = json.loads(response.strip())
            if not isinstance(data, dict):
                raise ValueError("LLM returned non-object JSON")
            return {
                "concept": data.get("concept", f"A bold image representing {topic}"),
                "composition": data.get("composition", "Center-focused composition with high contrast lighting."),
                "text_overlay": data.get("text_overlay", topic.split()[0].upper() if topic.split() else "WATCH THIS")[:3],
            }
        except Exception:
            return {
                "concept": f"A bold image representing {topic} with a surprised expression and contrasting colors.",
                "composition": "Center-focused composition with subject on left third, text overlay on right third.",
                "text_overlay": topic.split()[0].upper()[:3] if topic.split() else "WATCH THIS",
            }

    def _build_ai_prompt(self, concept: str, composition: str,
                          color_scheme: List[str], text: str) -> str:
        colors = ", ".join(color_scheme)
        return (f"Create a YouTube thumbnail. Concept: {concept} "
                f"Composition: {composition} "
                f"Color scheme: {colors} "
                f"Text overlay: '{text}' in bold white font with black stroke. "
                f"Style: photorealistic, high contrast, 1280x720.")


import json
