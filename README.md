# LogiclemonAI - Content Creator

A production-grade AI-powered YouTube content creation pipeline. Research topics, write scripts, optimize SEO, design thumbnails, and scale your YouTube channel - all automated.

## Features

- **🎬 Script Writing** - YouTube-optimized scripts with hooks, retention patterns, timestamps
- **🔍 Smart Research** - AI-powered research via Tavily + Firecrawl
- **📈 YouTube SEO** - Title optimization, tag generation, description with chapters
- **🖼️ Thumbnail Design** - AI-generated thumbnail concepts with composition guides
- **📋 Content Planning** - AI-generated content calendars for your niche
- **⚡ Batch Processing** - Create multiple videos at scale
- **🎯 CLI & Dashboard** - Full CLI tool + Web dashboard for managing your pipeline
- **📤 YouTube Publishing** - Upload, schedule, and manage videos via YouTube API
- **📊 Analytics** - Track video performance metrics

## Quick Start

### Prerequisites

- Python 3.11+
- OpenAI API key
- (Optional) Tavily API key for research
- (Optional) Google Cloud OAuth 2.0 credentials for YouTube upload

### Installation

```bash
git clone <repository>
cd LogiclemonAI
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configuration

```bash
cp .env.example .env
# Edit .env with your API keys
```

Required:
- `OPENAI_API_KEY` - Your OpenAI API key

Optional but recommended:
- `TAVILY_API_KEY` - For web research
- `YT_CLIENT_SECRET_FILE` - Google OAuth client_secret.json for YouTube uploads

### Usage

#### Web Dashboard
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Open http://localhost:8000/dashboard

#### CLI Tool
```bash
# Create a single video script
python -m app.cli create "How AI is Transforming Healthcare" --audience "tech enthusiasts" --show-script

# Batch create from topics file
python -m app.cli batch topics.txt --niche technology --output results.json

# Generate a monthly content plan
python -m app.cli plan "Machine Learning" --month "July 2025" --num 12

# Export script for TTS/narration
python -m app.cli export results.json --format tts --output narration.txt
```

#### API
```bash
# Create YouTube video content
curl -X POST "http://localhost:8000/api/v1/yt/create" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "How AI is Transforming Healthcare",
    "target_audience": "tech enthusiasts",
    "video_length": "medium",
    "tone": "professional",
    "niche": "technology"
  }'
```

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Input Topic                       │
└────────────────────┬────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────┐
│              1. Research Agent (Tavily + AI)         │
│     Gathers sources, key findings, statistics        │
└────────────────────┬────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────┐
│            2. Script Writer Agent (OpenAI)           │
│   Hook, sections with timestamps, conclusion, CTA   │
└────────────────────┬────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────┐
│            3. YouTube SEO Agent (OpenAI)             │
│  Title optimization, tags, description, chapters    │
└────────────────────┬────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────┐
│            4. Thumbnail Agent (OpenAI)               │
│   Concept, composition, colors, text overlay        │
└────────────────────┬────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────┐
│             5. Final Output Package                  │
│  Full script + SEO metadata + Thumbnail design      │
└─────────────────────────────────────────────────────┘
```

## Project Structure

```
LogiclemonAI/
├── app/
│   ├── agents/
│   │   ├── base_agent.py          # Abstract base class
│   │   ├── research_agent.py      # Tavily + Firecrawl research
│   │   ├── writer_agent.py        # Blog/article writer
│   │   ├── script_writer_agent.py # YouTube script writer
│   │   ├── youtube_seo_agent.py   # YouTube SEO optimizer
│   │   └── thumbnail_agent.py     # Thumbnail designer
│   ├── core/
│   │   ├── orchestrator.py        # Original content orchestrator
│   │   └── yt_pipeline.py         # YouTube pipeline orchestrator
│   ├── models/
│   │   ├── content.py             # Original content models
│   │   └── youtube.py             # YouTube-specific models
│   ├── services/
│   │   ├── database_service.py    # Supabase integration
│   │   └── youtube_service.py     # YouTube API v3 integration
│   ├── dashboard.py               # API router for YT endpoints
│   ├── cli.py                     # Command-line interface
│   ├── scheduler.py               # Upload scheduling system
│   ├── main.py                    # FastAPI application
│   ├── config.py                  # Configuration
│   └── static/
│       └── index.html             # Web dashboard
├── tests/
│   ├── test_agents.py
│   ├── test_orchestrator.py
│   ├── test_yt_pipeline.py
│   ├── test_script_writer.py
│   ├── test_seo_agent.py
│   ├── test_thumbnail_agent.py
│   └── test_cli.py
├── requirements.txt
├── .env.example
└── README.md
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_yt_pipeline.py -v
```

## YouTube API Setup

To enable YouTube upload and analytics:

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select existing
3. Enable YouTube Data API v3
4. Create OAuth 2.0 credentials (Desktop application type)
5. Download `client_secret.json` to project root
6. First upload will trigger OAuth flow (saves token to `yt_token.pickle`)

## Commercial Production Ready

This pipeline is built for scale:
- **Async architecture** handles concurrent video creation
- **Graceful degradation** when APIs are unavailable
- **Comprehensive error handling** at every stage
- **Modular agents** can be extended or replaced
- **Batch processing** for high-volume content operations
- **Scheduling system** for automated publishing

## License

MIT
