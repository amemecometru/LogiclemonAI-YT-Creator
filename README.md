# LogiclemonAI — YouTube Content Creator

An AI-powered YouTube content pipeline: research a topic, write the script, optimize SEO, render a thumbnail, plan a calendar — then optionally auto-post a launch thread to X. Vanilla "Glazier" web studio + FastAPI backend + Cloudflare Workers.

## Features

- **🎬 Script generation** — full YouTube scripts with hook, timestamped sections, conclusion, CTA
- **🔍 Research** — Cloudflare research worker (DuckDuckGo) **+ real YouTube Data v3** ranking videos merged in (LLM fallback when neither is configured)
- **📈 YouTube SEO** — title/tag/description optimization with chapters
- **🖼️ Thumbnail** — concept + composition + a rendered **1280×720 image** (via Pollinations; free, no key)
- **📋 Content plan** — monthly calendars for a niche · **⚡ Batch** generation
- **📊 Channel analytics** — `GET /api/v1/yt/channel` (stats + recent uploads, via YouTube OAuth)
- **𝕏 Auto-thread** — connect an X account (OAuth2 worker) and post a launch thread from a generated script
- **🔑 API keys** — real, server-issued, sha256-hashed keys with optional gating + monthly quota
- **🖥️ Studio** — single-page Glazier UI served at `/dashboard`

## Architecture

```
app/                     FastAPI
  agents/                research, script_writer, youtube_seo, thumbnail
  core/yt_pipeline.py    studio pipeline (research → script → seo → thumbnail)
  services/              database_service (D1 over HTTP), youtube_service (Data API v3)
  auth.py                API-key issuance + validation + quota
  dashboard.py           /api/v1/yt/* router
  main.py                app: /, /health, mounts /dashboard, includes the router
  static/index.html      Glazier studio
workers/
  logiclemonai-db        D1 CRUD (content_*, yt_videos, users/api_keys/subscriptions/usage)
  research-worker        DuckDuckGo search + scrape (optional KV cache)
  x-worker               X (Twitter) OAuth2 + post
```

## Quick start

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in keys (see below)
uvicorn app.main:app --reload --port 8000
# open http://localhost:8000/dashboard
```

## Environment (`.env`)

| Var | Need | Notes |
|---|---|---|
| `OPENAI_API_KEY` | **required** | OpenAI or OpenRouter key (all agents) |
| `OPENAI_MODEL` | rec | default `gpt-4o-mini` |
| `OPENAI_BASE_URL` | if OpenRouter | `https://openrouter.ai/api/v1` |
| `HTTP_REFERER`, `X_TITLE` | optional | OpenRouter attribution headers (`X_TITLE` ≠ Twitter) |
| `YOUTUBE_API_KEY` | research | YouTube Data v3 **API key** (public read). Legacy alias `LOGICLEMONAI_YT_API_KEY` also accepted. |
| `YT_OAUTH_CLIENT_ID` / `YT_OAUTH_CLIENT_SECRET` | analytics/upload | Desktop OAuth client (channel analytics) |
| `YT_TOKEN_FILE` | optional | OAuth token cache (default `yt_token.pickle`) |
| `CLOUDFLARE_DB_URL` | persistence | db-worker URL |
| `CLOUDFLARE_RESEARCH_URL` | research worker | research-worker URL |
| `CLOUDFLARE_API_TOKEN` | if workers | **shared string** you invent — must equal the db/research workers' `API_TOKEN` (NOT your Cloudflare account token) |
| `X_WORKER_URL` / `X_WORKER_TOKEN` | X feature | x-worker URL + its `API_TOKEN` |
| `REQUIRE_API_KEY` | optional | `true` to gate the spend endpoints (default off) |
| `MONTHLY_QUOTA` | optional | per-key monthly unit cap when gating is on (default 1000) |
| `CORS_ALLOW_ORIGINS` | optional | default `*`; lock down in prod |

> Note: a YouTube **API key** only unlocks public reads (search/stats). Uploads/analytics need the **OAuth** client. The pipeline currently produces a script/SEO/thumbnail package, not a video file.

## Cloudflare Workers

```bash
# D1 schema
wrangler d1 migrations apply <db>     # 0001 content, 0002 yt_videos, 0003 commerce
# shared token (use ONE value for the app's CLOUDFLARE_API_TOKEN + both workers)
cd workers/db-worker       && wrangler secret put API_TOKEN && wrangler deploy
cd workers/research-worker && wrangler secret put API_TOKEN && wrangler deploy   # optional: bind RESEARCH_CACHE KV
cd workers/x-worker        && wrangler kv namespace create X_KV \
   && wrangler secret put X_CLIENT_ID && wrangler secret put X_CLIENT_SECRET && wrangler secret put API_TOKEN \
   && wrangler deploy        # set X_REDIRECT_URI = <worker-url>/x/callback and register it in the X app
```

## API (selected)

- `POST /api/v1/yt/create` → `{task_id}` (background); poll `GET /api/v1/yt/tasks/{id}`
- `POST /api/v1/yt/batch`, `POST /api/v1/yt/plan`
- `GET /api/v1/yt/videos`, `GET /api/v1/yt/videos/{id}` (persisted)
- `GET /api/v1/yt/channel` (YouTube OAuth)
- `POST/GET/DELETE /api/v1/yt/keys` (API keys)
- `GET /api/v1/yt/x/config`, `POST /api/v1/yt/x/post` (X auto-thread proxy)

## Testing

```bash
pytest                 # or: pytest --cov=app
```

## License

MIT
