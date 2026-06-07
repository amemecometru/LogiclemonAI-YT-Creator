#!/usr/bin/env python3
import asyncio
import json
import sys
import os
from datetime import datetime, timedelta
from typing import Optional, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def print_header(text: str):
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def print_result(data: dict, indent: int = 2):
    print(json.dumps(data, indent=indent, default=str))


async def cmd_create(args):
    from app.core.yt_pipeline import YTPipeline
    pipeline = YTPipeline()

    topic = args.topic
    audience = args.audience or "general audience"
    length = args.length or "medium"
    tone = args.tone or "professional"
    niche = args.niche or "general"

    print_header(f"Creating Video: {topic}")
    print(f"  Audience: {audience}")
    print(f"  Length: {length}")
    print(f"  Tone: {tone}")
    print(f"  Niche: {niche}")
    print(f"\n  Processing...\n")

    result = await pipeline.create_video_content(
        topic=topic,
        target_audience=audience,
        video_length=length,
        tone=tone,
        niche=niche
    )

    if result["status"] == "success":
        script = result.get("script", {})
        meta = result.get("metadata", {})
        thumb = result.get("thumbnail_design", {})

        print(f"  ✅ {result['status'].upper()}")
        print(f"  ⏱  {result['execution_time']}s")
        print(f"\n  📰 Title: {script.get('title', 'N/A')}")
        print(f"  📝 Words: {script.get('word_count', 0)}")
        print(f"  ⏱  Duration: ~{script.get('estimated_duration_seconds', 0)}s")

        print(f"\n  🔍 SEO Metadata:")
        print(f"    Title: {meta.get('title', 'N/A')}")
        print(f"    Tags: {', '.join(meta.get('tags', [])[:5])}")
        print(f"    Title variants: {', '.join(result.get('title_variants', [])[:3])}")

        if thumb:
            print(f"\n  🖼  Thumbnail:")
            print(f"    Concept: {thumb.get('concept_description', 'N/A')[:100]}...")
            print(f"    Text overlay: {thumb.get('text_overlay', 'N/A')}")

        if args.output:
            output_path = args.output
            with open(output_path, "w") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"\n  💾 Saved to: {output_path}")

        if args.show_script:
            print(f"\n  {'─' * 50}")
            print(script.get("full_script", "N/A"))
            print(f"  {'─' * 50}")

        if args.show_description:
            print(f"\n  📄 Description:")
            print(f"  {'─' * 50}")
            print(meta.get("description", "N/A"))
            print(f"  {'─' * 50}")
    else:
        print(f"  ❌ FAILED: {result.get('message', 'Unknown error')}")

    return result


async def cmd_batch(args):
    from app.core.yt_pipeline import YTPipeline
    pipeline = YTPipeline()

    topics_file = args.topics
    if not os.path.exists(topics_file):
        print(f"Topics file not found: {topics_file}")
        return

    with open(topics_file) as f:
        topics = [line.strip() for line in f if line.strip()]

    if not topics:
        print("No topics found in file")
        return

    audience = args.audience or "general audience"
    length = args.length or "medium"
    tone = args.tone or "professional"
    niche = args.niche or "general"

    print_header(f"Batch Creating {len(topics)} Videos")

    results = await pipeline.create_batch(
        topics=topics,
        target_audience=audience,
        video_length=length,
        tone=tone,
        niche=niche
    )

    success_count = sum(1 for r in results if r["status"] == "success")
    print(f"\n  Results: {success_count}/{len(results)} succeeded")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"  Saved to: {args.output}")


async def cmd_plan(args):
    from app.core.yt_pipeline import YTPipeline
    pipeline = YTPipeline()

    niche = args.niche
    month = args.month or datetime.now().strftime("%B %Y")
    num = args.num or 8
    audience = args.audience or "general audience"

    print_header(f"Content Plan for '{niche}' - {month}")
    print(f"  Generating {num} video ideas...\n")

    result = await pipeline.generate_content_plan(niche, month, num, audience)

    if result["status"] == "success":
        plan = result.get("plan", {})
        videos = plan.get("videos", [])
        print(f"  ✅ Generated {len(videos)} video ideas\n")
        for i, v in enumerate(videos, 1):
            print(f"  {i:2d}. {v.get('title', 'N/A')}")
            print(f"      Keywords: {', '.join(v.get('keywords', []))}")
            print(f"      Length: {v.get('suggested_length', 'N/A')}")
            print()

        if args.output:
            with open(args.output, "w") as f:
                json.dump(plan, f, indent=2)
            print(f"  Saved to: {args.output}")
    else:
        print(f"  ❌ FAILED: {result.get('message', '')}")


async def cmd_export_for_tts(args):
    import json

    input_file = args.input
    if not os.path.exists(input_file):
        print(f"File not found: {input_file}")
        return

    with open(input_file) as f:
        data = json.load(f)

    script = data.get("script") or data
    full_script = script.get("full_script", "")
    sections = script.get("sections", [])

    if args.format == "plain":
        print(full_script)
    elif args.format == "sections":
        for sec in sections:
            print(f"\n[{sec.get('timestamp', '0:00')}] {sec.get('title', '')}")
            print(sec.get("content", ""))
    elif args.format == "tts":
        tts_text = full_script
        tts_text = tts_text.replace("#", "").replace("*", "")
        print(tts_text.strip())

    if args.output:
        ext = ".txt" if args.format == "plain" else ".txt"
        output_path = args.output
        with open(output_path, "w") as f:
            if args.format == "plain":
                f.write(full_script)
            elif args.format == "sections":
                for sec in sections:
                    f.write(f"\n[{sec.get('timestamp', '0:00')}] {sec.get('title', '')}\n")
                    f.write(sec.get("content", "") + "\n")
            else:
                tts_text = full_script.replace("#", "").replace("*", "")
                f.write(tts_text.strip())
        print(f"Saved to: {output_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="LogiclemonAI - Content Creator Pipeline CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  contento create "AI in Healthcare" --audience "tech enthusiasts" --show-script
  contento batch topics.txt --niche technology --output results.json
  contento plan "Machine Learning" --num 12 --month "July 2025"
  contento export result.json --format tts --output narration.txt
        """
    )
    subparsers = parser.add_subparsers(dest="command")

    create_parser = subparsers.add_parser("create", help="Create a single video script")
    create_parser.add_argument("topic", help="Video topic")
    create_parser.add_argument("--audience", "-a", default="general audience", help="Target audience")
    create_parser.add_argument("--length", "-l", choices=["short", "medium", "long"], default="medium", help="Video length")
    create_parser.add_argument("--tone", "-t", default="professional", help="Content tone")
    create_parser.add_argument("--niche", "-n", default="general", help="Content niche")
    create_parser.add_argument("--output", "-o", help="Save result to JSON file")
    create_parser.add_argument("--show-script", action="store_true", help="Print full script")
    create_parser.add_argument("--show-description", action="store_true", help="Print description")

    batch_parser = subparsers.add_parser("batch", help="Batch create from topics file")
    batch_parser.add_argument("topics", help="File with one topic per line")
    batch_parser.add_argument("--audience", "-a", default="general audience")
    batch_parser.add_argument("--length", "-l", choices=["short", "medium", "long"], default="medium")
    batch_parser.add_argument("--tone", "-t", default="professional")
    batch_parser.add_argument("--niche", "-n", default="general")
    batch_parser.add_argument("--output", "-o", help="Save results to JSON file")

    plan_parser = subparsers.add_parser("plan", help="Generate a content plan")
    plan_parser.add_argument("niche", help="Channel niche")
    plan_parser.add_argument("--month", "-m", help="Month (e.g. 'July 2025')")
    plan_parser.add_argument("--num", type=int, default=8, help="Number of video ideas")
    plan_parser.add_argument("--audience", "-a", default="general audience")
    plan_parser.add_argument("--output", "-o", help="Save plan to JSON file")

    export_parser = subparsers.add_parser("export", help="Export script for TTS/narration")
    export_parser.add_argument("input", help="Input JSON file from create command")
    export_parser.add_argument("--format", "-f", choices=["plain", "sections", "tts"], default="plain", help="Export format")
    export_parser.add_argument("--output", "-o", help="Output file path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "create":
        asyncio.run(cmd_create(args))
    elif args.command == "batch":
        asyncio.run(cmd_batch(args))
    elif args.command == "plan":
        asyncio.run(cmd_plan(args))
    elif args.command == "export":
        asyncio.run(cmd_export_for_tts(args))


if __name__ == "__main__":
    main()
