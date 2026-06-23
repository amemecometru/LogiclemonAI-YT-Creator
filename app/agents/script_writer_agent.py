import json
import re
from typing import Dict, Any, List
from app.agents.base_agent import BaseAgent
from app.models.content import AgentType, ContentStatus
from app.models.youtube import VideoScript, ScriptSection, VideoLength


class ScriptWriterAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.WRITER)
        self.intro_durations = {"short": 15, "medium": 30, "long": 60}
        self.section_durations = {"short": 30, "medium": 60, "long": 120}

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        self.update_status(ContentStatus.PROCESSING)

        try:
            if not await self.validate_input(input_data):
                raise ValueError("Invalid input data for script writer agent")

            topic = input_data.get("topic", "")
            research_data = input_data.get("research_data", {})
            target_audience = input_data.get("target_audience", "general audience")
            video_length = input_data.get("video_length", VideoLength.MEDIUM)
            tone = input_data.get("tone", "professional")
            model = input_data.get("model")
            byok_key = input_data.get("byok_key")
            target_duration = self._get_target_duration(video_length)

            elements = await self._generate_all_elements(topic, research_data, target_audience, model=model, byok_key=byok_key)
            title = elements.get("title", topic)
            hook = elements.get("hook", "")
            conclusion = elements.get("conclusion", "")
            call_to_action = elements.get("call_to_action", "")
            sections = await self._generate_sections(topic, research_data, target_duration, target_audience, tone, model=model, byok_key=byok_key)

            full_script_parts = [f"# {title}\n"]
            full_script_parts.append(f"## Hook\n{hook}\n")
            for sec in sections:
                full_script_parts.append(f"## [{sec.timestamp}] {sec.title}\n{sec.content}\n")
            full_script_parts.append(f"## Conclusion\n{conclusion}\n")
            full_script_parts.append(f"## Call to Action\n{call_to_action}\n")
            full_script = "\n".join(full_script_parts)

            total_duration = sum(s.duration_seconds for s in sections)
            total_words = len(full_script.split())

            key_findings = research_data.get("key_findings", [])
            key_points = key_findings[:5] if key_findings else [f"Key insight about {topic}"]

            video_script = VideoScript(
                topic=topic,
                title=title,
                hook=hook,
                sections=sections,
                conclusion=conclusion,
                call_to_action=call_to_action,
                full_script=full_script,
                estimated_duration_seconds=total_duration,
                word_count=total_words,
                target_audience=target_audience,
                tone=tone,
                key_points=key_points
            )

            self.update_status(ContentStatus.COMPLETED)

            return {
                "status": "success",
                "script": video_script.model_dump()
            }

        except Exception as e:
            self.update_status(ContentStatus.FAILED)
            return {
                "status": "error",
                "message": str(e),
                "script": None
            }

    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        required = ["topic"]
        return all(f in input_data and input_data[f] for f in required)

    def _get_target_duration(self, video_length: VideoLength) -> int:
        mapping = {VideoLength.SHORT: 60, VideoLength.MEDIUM: 480, VideoLength.LONG: 1200}
        return mapping.get(video_length, 480)

    async def _generate_all_elements(self, topic: str, research_data: Dict[str, Any], audience: str, model: str | None = None, byok_key: str | None = None) -> Dict[str, str]:
        findings = research_data.get("key_findings", [])
        findings_text = "\n".join(f"- {f}" for f in findings[:3])

        prompt = f"""Generate the title, hook, conclusion, and call-to-action for a YouTube video about "{topic}" for {audience}.

Research context:
{findings_text}

Requirements:
- Title: 30-60 characters, clickable, SEO-friendly, power words
- Hook: 30-40 words, starts with a pattern interrupt (question or bold statement), creates curiosity gap
- Conclusion: ~60 words, summarizes key takeaway, reinforces the main message
- Call-to-action: ~50 words, ask for like/subscribe/comment, mention next video topic

Return as JSON only:
{{
    "title": "...",
    "hook": "...",
    "conclusion": "...",
    "call_to_action": "..."
}}"""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, model=model, byok_key=byok_key, max_tokens=500, temperature=0.8)
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            parsed = json.loads(response.strip())
            if not isinstance(parsed, dict):
                raise ValueError("LLM returned non-object JSON")
            return parsed
        except Exception:
            return {
                "title": f"The Truth About {topic}"[:60],
                "hook": f"Most people don't know this about {topic}, but after watching this video, you'll never look at it the same way again.",
                "conclusion": f"In conclusion, {topic} is something everyone should understand. The key takeaways will help you make better decisions going forward.",
                "call_to_action": f"If you found this helpful, hit like and subscribe. Comment below what you think about {topic}. Next video we dive even deeper."
            }

    async def _generate_sections(self, topic: str, research_data: Dict[str, Any],
                                  target_duration: int, audience: str, tone: str,
                                  model: str | None = None, byok_key: str | None = None) -> List[ScriptSection]:
        num_sections = max(3, min(6, target_duration // 90))
        sec_duration = target_duration // num_sections

        findings = research_data.get("key_findings", [])
        findings_text = "\n".join(f"- {f}" for f in findings[:5])
        args = research_data.get("main_arguments", [])
        args_text = "\n".join(f"- {a}" for a in args[:3])

        prompt = f"""Create a structured outline for a YouTube video about "{topic}" with {num_sections} sections.

Target audience: {audience}
Tone: {tone}
Each section: ~{sec_duration} seconds

Research findings:
{findings_text}

Main arguments:
{args_text}

Return JSON array:
[
  {{
    "title": "Section title",
    "content": "What to say in this section (~{sec_duration * 2} words)",
    "visual_cue": "what to show on screen"
  }}
]

Return ONLY valid JSON array."""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, model=model, byok_key=byok_key, max_tokens=2000, temperature=0.7)
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            raw_sections = json.loads(response)
            if not isinstance(raw_sections, list):
                raise ValueError("LLM returned non-list JSON for sections")
            sections = []
            current_time = 0
            for i, rs in enumerate(raw_sections[:num_sections]):
                minutes = current_time // 60
                seconds = current_time % 60
                timestamp = f"{minutes}:{seconds:02d}"
                sections.append(ScriptSection(
                    timestamp=timestamp,
                    duration_seconds=sec_duration,
                    title=rs.get("title", f"Section {i+1}") if isinstance(rs, dict) else f"Section {i+1}",
                    content=rs.get("content", "") if isinstance(rs, dict) else "",
                    visual_cue=rs.get("visual_cue") if isinstance(rs, dict) else None
                ))
                current_time += sec_duration

            return sections

        except (json.JSONDecodeError, Exception) as e:
            print(f"Error generating sections: {e}")
            return self._generate_fallback_sections(topic, num_sections, sec_duration)

    def _generate_fallback_sections(self, topic: str, num: int, duration: int) -> List[ScriptSection]:
        sections = []
        starters = [
            ("What is it?", f"Let's start by understanding what {topic} really means."),
            ("Why It Matters", f"Here's why {topic} is more important than you think."),
            ("How It Works", f"Let me break down exactly how {topic} works."),
            ("Key Benefits", f"Here are the biggest benefits of {topic}."),
            ("Common Mistakes", f"Most people make these mistakes with {topic}."),
            ("Final Tips", f"Here are my final tips for mastering {topic}.")
        ]
        for i in range(num):
            title, content = starters[i % len(starters)]
            minutes = (i * duration) // 60
            seconds = (i * duration) % 60
            sections.append(ScriptSection(
                timestamp=f"{minutes}:{seconds:02d}",
                duration_seconds=duration,
                title=title,
                content=content,
                visual_cue=f"Visual showing {topic}"
            ))
        return sections


