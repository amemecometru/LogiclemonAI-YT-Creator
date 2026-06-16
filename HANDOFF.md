# LogiclemonAI YT-Creator — Build Handoff & Roadmap to v1

> Purpose: give Opencode everything needed to finish this project, in priority order.
> Each task = its own branch + PR. The operator (Malachi) supplies any credentials a task needs.

---

## 0. Ground rules for Opencode
- **Repo:** `amemecometru/Logiclemonai-yt` (stable id **1262386010**, default branch `main`). If a push by name 307-redirects, use the id endpoint `/repositories/1262386010/...`.
- **Apply changes exactly as specified.** Don't re-architect untouched files. The Glazier frontend, the agents, and `client.js`-style engines are intentional — extend, don't rewrite.
- **One PR per task** (suggested branch names below). Keep diffs scoped.
- **Secrets never get committed.** App secrets → `.env`; worker secrets → `wrangler secret put`. Add `.gitignore` entries (see T2).
- **Workers are fail-closed:** they 500 unless `API_TOKEN` is set; the app must send a matching token.
- **`wrangler dev` crashes locally on ChromeOS/Crostini** — use `wrangler deploy` (or `--remote`).

## 1. Architecture (what exists)
```
FastAPI app (app/)
  agents/         research, script_writer, youtube_seo, thumbnail  (+ writer = legacy)
  core/           yt_pipeline (studio pipeline)   orchestrator (legacy content pipeline)
  services/       database_service (D1 over HTTP)  youtube_service (Google API, desktop OAuth)
  dashboard.py    /api/v1/yt/* router  (create/tasks/plan/batch/videos/export + x/config + x/post)
  main.py         app, mounts /dashboard static, includes router
  config.py       pydantic settings (.env)
  static/index.html   Glazier studio (served at /dashboard)
Cloudflare Workers (workers/)
  logiclemonai-db   D1 CRUD (content_* + yt_videos)
  research-worker   DuckDuckGo scrape
  x-worker          X (Twitter) OAuth2 PKCE + POST /x/post
```

## 2. Current state
**Merged to `main`:**
- Glazier UI restyle; non-blocking `POST /api/v1/yt/create` (FastAPI background task) + poll `GET /api/v1/yt/tasks/{id}`; D1 persistence (`yt_videos` table, migration `0002`) so generated scripts survive a restart; **Library** tab.
- Security/robustness: fail-closed worker auth, CORS fixed (`*`+credentials removed), UUID task ids, bounded in-memory task store, working `/export`.
- X integration: `workers/x-worker` (OAuth2 PKCE connect + `/x/post`), FastAPI proxy `/api/v1/yt/x/{config,post}` (worker token stays server-side), frontend 𝕏 connect chip + **editable thread composer**.

**Open PR:** #4 — X thread composer. **→ merge it first (T1).**

## 3. Credentials & environment (full inventory)
### App `.env`
| Var | Need | Notes |
|---|---|---|
| `OPENAI_API_KEY` | **required** | OpenAI or OpenRouter key (all agents) |
| `OPENAI_MODEL` | rec | default `gpt-4o-mini`; OpenRouter slug if applicable |
| `OPENAI_BASE_URL` | if OpenRouter | `https://openrouter.ai/api/v1` |
| `HTTP_REFERER`, `X_TITLE` | optional | OpenRouter attribution headers (`X_TITLE` ≠ Twitter) |
| `CLOUDFLARE_DB_URL` | persistence | db-worker URL |
| `CLOUDFLARE_RESEARCH_URL` | research | research-worker URL |
| `CLOUDFLARE_API_TOKEN` | if workers | **shared invented string** = db+research worker `API_TOKEN`. NOT a real Cloudflare token. |
| `CORS_ALLOW_ORIGINS` | optional | default `*`; lock down in prod |
| `X_WORKER_URL` | X feature | x-worker base URL |
| `X_WORKER_TOKEN` | X feature | = x-worker `API_TOKEN` |
| `LOGICLEMONAI_YT_API_KEY` | YT research | YouTube Data v3 **API key** (public read) — wired in T3 (rename to `YOUTUBE_API_KEY` or read both) |
| `YT_OAUTH_CLIENT_ID` / `YT_OAUTH_CLIENT_SECRET` | YT OAuth | desktop client creds — used by T2 |
| `YT_TOKEN_FILE` | YT OAuth | token cache path (default `yt_token.pickle`) |

### Worker secrets (`wrangler secret put`)
- **logiclemonai-db**, **research-worker**: `API_TOKEN` (same value as app `CLOUDFLARE_API_TOKEN`).
- **x-worker**: `X_CLIENT_ID`, `X_CLIENT_SECRET`, `API_TOKEN` (= app `X_WORKER_TOKEN`); KV namespace `X_KV`; vars `X_REDIRECT_URI`, `X_SCOPES`.
- **Wrangler auth** for deploys = `wrangler login` (separate from everything above).

## 4. Deploy/ops checklist (lights up what's already built)
1. `wrangler d1 migrations apply <db>` (applies `0002_yt_videos`).
2. `wrangler secret put API_TOKEN` on db + research workers (shared value).
3. Deploy **x-worker**: `wrangler kv namespace create X_KV` → id into `wrangler.toml`; `wrangler secret put X_CLIENT_ID|X_CLIENT_SECRET|API_TOKEN`; set `X_REDIRECT_URI` = `<worker-url>/x/callback`; `wrangler deploy`; register that callback in the X app.
4. App `.env`: set `CLOUDFLARE_DB_URL`, `CLOUDFLARE_RESEARCH_URL`, `CLOUDFLARE_API_TOKEN`, `X_WORKER_URL`, `X_WORKER_TOKEN`.
5. Smoke test: generate a script → restart API → confirm it's still in **Library**; connect X → post a thread.

---

## 5. ROADMAP (ordered; each item is a PR)

### Phase 1 — finish what's started
**T1 · Merge PR #4** (X composer).

**T2 · YouTube Data v3 OAuth** — branch `yt-oauth-env`. Creds: operator's desktop `YT_OAUTH_CLIENT_ID`/`SECRET`.
- Google side (operator): enable **YouTube Data API v3**; OAuth consent screen (External) with the 4 scopes `youtube.upload`, `youtube`, `youtubepartner`, `youtube.force-ssl`; add operator as **Test user**.
- Code: patch `app/services/youtube_service.py` `_authenticate()` to build the flow via `InstalledAppFlow.from_client_config({...installed...}, SCOPES)` reading `YT_OAUTH_CLIENT_ID`/`YT_OAUTH_CLIENT_SECRET` from settings, **keeping the `from_client_secrets_file` path as fallback**. Add `config.py` settings.
- Add `.gitignore`: `.env`, `client_secret.json`, `yt_token.pickle`, `__pycache__/`, `*.pyc`.
- Done when: first run opens browser consent locally and caches `yt_token.pickle`; subsequent runs auth silently.

**T3 · Real YouTube research** — branch `yt-research`. Creds: `LOGICLEMONAI_YT_API_KEY`.
- In `app/agents/research_agent.py`, add a YouTube Data v3 `search.list` + `videos.list` step (httpx, API-key) that pulls top videos (title, channel, views, publishedAt) for the topic and merges into `research_data` (`sources`, `key_findings`, a new `youtube_competitors` field).
- `config.py`: `youtube_api_key` (read `YOUTUBE_API_KEY` or `LOGICLEMONAI_YT_API_KEY`). No-op gracefully if unset.
- Done when: a generated script's research reflects real ranking videos when the key is set.

### Phase 2 — make the OUTPUT real (today it ships briefs, not assets)
**T4 · Thumbnail image generation** — branch `thumbnail-image`. Creds: an image-model key (operator picks OpenAI Images / Gemini / Stability).
- After `thumbnail_agent` produces `ai_generation_prompt`, call the image API to render a real **1280×720** thumbnail; store it (Cloudflare **R2** or return a data/URL) and add `thumbnail_url` to the pipeline result + Library + the result card.
- Done when: each generated video has a viewable thumbnail image, not just a prompt.

**T5 · Channel analytics (OAuth)** — branch `yt-analytics`. Uses T2 creds.
- `GET /api/v1/yt/channel` → `youtube_service.get_channel_stats()` + recent videos; add a **Channel** tab/card in the studio.
- Done when: the connected channel's subs/views/recent videos render.

### Phase 3 — commercial foundation (monetization) — the real gate to "product"
**T6 · D1 schema** — branch `commerce-schema`. Migration `0003`: `users`, `api_keys`, `subscriptions`, `usage` (see acceptance below). Add db-worker routes for each (mirror existing CRUD).

**T7 · Auth + real API keys** — branch `auth-apikeys`.
- Replace the **client-side fake** `generateApiKey()` with server-issued keys: `POST /api/v1/keys` (create, returns once, store hash), `GET /api/v1/keys`, `DELETE /api/v1/keys/{id}`; validate on every `/api/v1/yt/*` call via middleware/dependency; enforce per-key monthly quota from `usage`.
- Minimal user identity: email+password (hashed) or reuse the X/Google OAuth. Sessions or signed tokens.
- Done when: requests without a valid key are 401; the studio's API-key panel shows real keys.

**T8 · Stripe (TEST keys first)** — branch `billing-stripe`. Creds: Stripe **test** secret + price ids + webhook secret.
- `POST /api/v1/billing/checkout` → Stripe Checkout Session for Monthly ($10) / Annual ($50); `POST /api/v1/billing/webhook` → set `subscriptions.status`; gate features + quota by plan. Wire the existing Pricing "Subscribe" buttons (replace the stub modal) to real checkout.
- Done when: test-card checkout flips a user to active and unlocks the plan; the stub alert is gone.

### Phase 4 — hardening & cleanup
- **T9 · Research robustness** (`research-worker`): the DuckDuckGo-Lite scrape is brittle and rate-limited — add KV caching + a fallback source (T3's YouTube data helps); handle non-200s.
- **T10 · Concurrency**: FastAPI `BackgroundTasks` is fine at low volume; move to a durable queue (Cloudflare Queues / Celery+Redis) before scaling.
- **T11 · Dead code**: `app/scheduler.py` is never started and the legacy content pipeline (`orchestrator.py` + `writer_agent.py`) is unused by the studio — wire intentionally or remove.
- **T12 · Tests & docs**: make `tests/` pass against the new endpoints; refresh `README.md` (drop the stale `TAVILY_API_KEY` mention; document the X + YouTube flows, the env table, and the deploy checklist).

---

## 6. Acceptance criteria (key items)
- **T6 schema (D1):**
  - `users(id, email, password_hash?, oauth_provider?, oauth_sub?, plan, created_at)`
  - `api_keys(id, user_id, name, key_hash, prefix, last_used_at, revoked, created_at)`
  - `subscriptions(id, user_id, stripe_customer_id, stripe_sub_id, plan, status, current_period_end)`
  - `usage(id, user_id, period, units, updated_at)`
- **Security:** no endpoint that performs work or spends LLM/API budget is reachable without a valid key/session once T7 lands. Stripe keys are **test** until launch.
- **Quotas:** monthly unit cap per plan enforced from `usage`; 402/429 when exceeded.

## 7. Known constraints / gotchas
- Desktop YouTube OAuth = **local only** (needs a browser); Testing-mode sensitive scopes → **refresh token expires ~7 days** until the OAuth app is Published/verified.
- YouTube Data v3 quota: **10,000 units/day** (search ≈ 100, upload ≈ 1,600).
- `Response.redirect()` in Workers needs an **absolute** URL.
- Stripe account is currently **LIVE** keys — create/use **TEST** keys for all dev (T8).
- Don't commit `.env`, `client_secret.json`, `yt_token.pickle` (T2 adds `.gitignore`).
