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
            target_duration = self._get_target_duration(video_length)

            title = await self._generate_title(topic, research_data, target_audience)
            hook = await self._generate_hook(topic, target_audience)
            sections = await self._generate_sections(topic, research_data, target_duration, target_audience, tone)
            conclusion = await self._generate_conclusion(topic, sections)
            call_to_action = await self._generate_cta(topic, target_audience)

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

    async def _generate_title(self, topic: str, research_data: Dict[str, Any], audience: str) -> str:
        findings = research_data.get("key_findings", [])
        findings_text = "\n".join(f"- {f}" for f in findings[:3])

        prompt = f"""Generate a compelling YouTube video title about "{topic}" for {audience}.

Research context:
{findings_text}

Requirements:
- 30-60 characters
- Clickable and curiosity-driven
- Include a key benefit or surprising fact
- Use power words
- SEO-friendly

Return ONLY the title string, no quotes, no explanation."""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, max_tokens=100, temperature=0.8)
            return response.strip().strip('"\'')
        except Exception as e:
            fallback = f"The Truth About {topic}"
            return fallback[:60]

    async def _generate_hook(self, topic: str, audience: str) -> str:
        prompt = f"""Write a powerful 15-30 second video hook about "{topic}" for {audience}.

The hook must:
- Start with a pattern interrupt (question, bold statement, or surprising fact)
- Create curiosity gap
- Make them want to watch the whole video
- Be spoken in 30-40 words max

Return ONLY the hook text."""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, max_tokens=150, temperature=0.8)
            return response.strip()
        except Exception:
            return f"Most people don't know this about {topic}, but after watching this video, you'll never look at it the same way again."

    async def _generate_sections(self, topic: str, research_data: Dict[str, Any],
                                  target_duration: int, audience: str, tone: str) -> List[ScriptSection]:
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
            response = await self.call_openai(messages, max_tokens=2000, temperature=0.7)
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            raw_sections = json.loads(response)
            sections = []
            current_time = 0
            for i, rs in enumerate(raw_sections[:num_sections]):
                minutes = current_time // 60
                seconds = current_time % 60
                timestamp = f"{minutes}:{seconds:02d}"
                sections.append(ScriptSection(
                    timestamp=timestamp,
                    duration_seconds=sec_duration,
                    title=rs.get("title", f"Section {i+1}"),
                    content=rs.get("content", ""),
                    visual_cue=rs.get("visual_cue")
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

    async def _generate_conclusion(self, topic: str, sections: List[ScriptSection]) -> str:
        prompt = f"""Write a 30-second conclusion for a YouTube video about "{topic}".

Summarize the key points and reinforce the main takeaway.
Keep it concise and impactful. ~60 words.

Return ONLY the conclusion text."""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, max_tokens=200, temperature=0.7)
            return response.strip()
        except Exception:
            return f"In conclusion, {topic} is something everyone should understand. The key takeaways from this video will help you make better decisions going forward."

    async def _generate_cta(self, topic: str, audience: str) -> str:
        prompt = f"""Write a call to action for a YouTube video about "{topic}" for {audience}.

Include:
- Ask to like the video
- Ask to subscribe with a reason
- Ask to comment (specific question related to {topic})
- Mention what the next video will be about

Return ONLY the CTA text, ~50 words."""

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.call_openai(messages, max_tokens=200, temperature=0.7)
            return response.strip()
        except Exception:
            return "If you found this helpful, hit that like button and subscribe for more content like this. Leave a comment below telling me what you think about " + topic + ". And don't miss next week's video where we dive even deeper!"
