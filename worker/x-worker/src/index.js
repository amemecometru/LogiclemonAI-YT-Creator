/**
 * x-worker — X (Twitter) OAuth2 + post worker for LogiclemonAI YT-Creator.
 *
 * Routes:
 *   GET  /x/login      → start OAuth2 (PKCE), redirect the browser to X authorize
 *   GET  /x/callback   → exchange code for tokens, store in KV, redirect to success
 *   GET  /x/status     → { connected, username }  (public; no secrets returned)
 *   POST /x/post       → post a tweet/thread (GATED by API_TOKEN). Body:
 *                          { "thread": ["t1","t2", ...] }  or  { "text": "..." }
 *
 * Single-account MVP: tokens are stored in KV under a fixed key ("tokens:default").
 * For multi-tenant later, key tokens by user id and pass that through login/state.
 *
 * Bindings (wrangler.toml):
 *   - KV namespace  X_KV
 *   - vars:    X_REDIRECT_URI, X_SCOPES, POST_SUCCESS_REDIRECT
 *   - secrets: X_CLIENT_ID, X_CLIENT_SECRET, API_TOKEN
 *
 * X endpoints (twitter.com hosts are the long-stable ones; x.com hosts also work).
 */

const AUTHORIZE_URL = "https://twitter.com/i/oauth2/authorize";
const TOKEN_URL = "https://api.twitter.com/2/oauth2/token";
const API_BASE = "https://api.twitter.com/2";
const TOKENS_KEY = "tokens:default";
const DEFAULT_SCOPES = "tweet.read tweet.write users.read offline.access";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/^\/x-worker/, ""); // tolerate a route prefix

    if (request.method === "OPTIONS") return cors(new Response(null, { status: 204 }));

    try {
      if (request.method === "GET" && path === "/x/login") return handleLogin(env);
      if (request.method === "GET" && path === "/x/callback") return handleCallback(request, env, url);
      if (request.method === "GET" && path === "/x/status") return handleStatus(env);
      if (request.method === "POST" && path === "/x/post") return handlePost(request, env);
      if (path === "/" || path === "") {
        return cors(json({ service: "x-worker", routes: ["/x/login", "/x/callback", "/x/status", "POST /x/post"] }));
      }
      return cors(json({ error: "Not found" }, 404));
    } catch (err) {
      return cors(json({ error: String(err && err.message || err) }, 500));
    }
  },
};

/* ----------------------------- OAuth: login ----------------------------- */
async function handleLogin(env) {
  if (!env.X_CLIENT_ID) return cors(json({ error: "Server misconfigured: X_CLIENT_ID not set" }, 500));
  const redirectUri = env.X_REDIRECT_URI;
  if (!redirectUri) return cors(json({ error: "Server misconfigured: X_REDIRECT_URI not set" }, 500));

  const verifier = b64url(crypto.getRandomValues(new Uint8Array(32)));
  const challenge = b64url(await sha256(verifier));
  const state = b64url(crypto.getRandomValues(new Uint8Array(16)));

  // stash the verifier keyed by state so /x/callback can complete PKCE (10 min TTL)
  await env.X_KV.put(`pkce:${state}`, verifier, { expirationTtl: 600 });

  const params = new URLSearchParams({
    response_type: "code",
    client_id: env.X_CLIENT_ID,
    redirect_uri: redirectUri,
    scope: env.X_SCOPES || DEFAULT_SCOPES,
    state,
    code_challenge: challenge,
    code_challenge_method: "S256",
  });
  return Response.redirect(`${AUTHORIZE_URL}?${params.toString()}`, 302);
}

/* ---------------------------- OAuth: callback ---------------------------- */
async function handleCallback(request, env, url) {
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const oauthErr = url.searchParams.get("error");
  if (oauthErr) return cors(html(`<h2>X authorization failed</h2><p>${escapeHtml(oauthErr)}</p>`, 400));
  if (!code || !state) return cors(json({ error: "Missing code or state" }, 400));

  const verifier = await env.X_KV.get(`pkce:${state}`);
  if (!verifier) return cors(json({ error: "Invalid or expired state — restart at /x/login" }, 400));
  await env.X_KV.delete(`pkce:${state}`);

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: env.X_REDIRECT_URI,
    code_verifier: verifier,
    client_id: env.X_CLIENT_ID,
  });

  const tokenResp = await fetch(TOKEN_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: "Basic " + btoa(`${env.X_CLIENT_ID}:${env.X_CLIENT_SECRET}`),
    },
    body: body.toString(),
  });
  const tok = await tokenResp.json();
  if (!tokenResp.ok || !tok.access_token) {
    return cors(html(`<h2>Token exchange failed</h2><pre>${escapeHtml(JSON.stringify(tok, null, 2))}</pre>`, 400));
  }

  const username = await fetchUsername(tok.access_token);
  await saveTokens(env, tok, username);

  const dest = env.POST_SUCCESS_REDIRECT;
  if (dest && /^https?:\/\//.test(dest)) return Response.redirect(dest, 302);
  return cors(html(`<h2>✅ Connected to X${username ? " as @" + escapeHtml(username) : ""}</h2><p>You can close this tab and return to the studio.</p>`));
}

/* ------------------------------- status -------------------------------- */
async function handleStatus(env) {
  const t = await loadTokens(env);
  return cors(json({ connected: !!(t && t.access_token), username: (t && t.username) || null }));
}

/* -------------------------------- post --------------------------------- */
async function handlePost(request, env) {
  // gate: server-to-server only (never expose API_TOKEN in client JS)
  if (!env.API_TOKEN) return cors(json({ error: "Server misconfigured: API_TOKEN not set" }, 500));
  const auth = request.headers.get("Authorization") || "";
  const provided = auth.replace(/^Bearer\s+/i, "");
  if (provided !== env.API_TOKEN) return cors(json({ error: "Unauthorized" }, 401));

  let payload;
  try { payload = await request.json(); } catch { return cors(json({ error: "Invalid JSON body" }, 400)); }

  let tweets = [];
  if (Array.isArray(payload.thread)) tweets = payload.thread.map((s) => String(s || "").trim()).filter(Boolean);
  else if (payload.text) tweets = [String(payload.text).trim()];
  if (!tweets.length) return cors(json({ error: "Provide { thread: [...] } or { text: '...' }" }, 400));
  if (tweets.some((t) => t.length > 280)) return cors(json({ error: "Each tweet must be <= 280 characters" }, 400));

  const accessToken = await getValidAccessToken(env);
  if (!accessToken) return cors(json({ error: "X not connected — visit /x/login first" }, 409));

  const posted = [];
  let replyTo = null;
  for (const text of tweets) {
    const tweetBody = replyTo ? { text, reply: { in_reply_to_tweet_id: replyTo } } : { text };
    const r = await fetch(`${API_BASE}/tweets`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify(tweetBody),
    });
    const data = await r.json();
    if (!r.ok || !data.data || !data.data.id) {
      return cors(json({ error: "Tweet failed", posted, detail: data }, 502));
    }
    replyTo = data.data.id;
    posted.push(data.data.id);
  }

  const t = await loadTokens(env);
  const handle = (t && t.username) || "i";
  return cors(json({ status: "success", posted, count: posted.length, url: `https://x.com/${handle}/status/${posted[0]}` }));
}

/* ------------------------------ token mgmt ----------------------------- */
async function getValidAccessToken(env) {
  const t = await loadTokens(env);
  if (!t || !t.access_token) return null;
  if (Date.now() < (t.expires_at || 0) - 60000) return t.access_token; // still valid (60s skew)
  if (!t.refresh_token) return t.access_token; // no refresh available — try as-is

  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: t.refresh_token,
    client_id: env.X_CLIENT_ID,
  });
  const r = await fetch(TOKEN_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: "Basic " + btoa(`${env.X_CLIENT_ID}:${env.X_CLIENT_SECRET}`),
    },
    body: body.toString(),
  });
  const tok = await r.json();
  if (!r.ok || !tok.access_token) return t.access_token; // refresh failed — fall back, post may 401
  await saveTokens(env, tok, t.username, t.refresh_token);
  return tok.access_token;
}

async function saveTokens(env, tok, username, prevRefresh) {
  const record = {
    access_token: tok.access_token,
    refresh_token: tok.refresh_token || prevRefresh || null, // X rotates refresh tokens
    expires_at: Date.now() + (tok.expires_in ? tok.expires_in * 1000 : 7200000),
    username: username || null,
    scope: tok.scope || null,
  };
  await env.X_KV.put(TOKENS_KEY, JSON.stringify(record));
}

async function loadTokens(env) {
  const raw = await env.X_KV.get(TOKENS_KEY);
  return raw ? JSON.parse(raw) : null;
}

async function fetchUsername(accessToken) {
  try {
    const r = await fetch(`${API_BASE}/users/me`, { headers: { Authorization: `Bearer ${accessToken}` } });
    const d = await r.json();
    return d && d.data && d.data.username ? d.data.username : null;
  } catch { return null; }
}

/* ------------------------------- helpers ------------------------------- */
function b64url(bytes) {
  let s = btoa(String.fromCharCode(...new Uint8Array(bytes)));
  return s.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
async function sha256(str) {
  return crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
}
function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json" } });
}
function html(inner, status = 200) {
  return new Response(`<!doctype html><meta charset="utf-8"><body style="font-family:system-ui;background:#070b12;color:#e6edf5;padding:40px;">${inner}</body>`, {
    status, headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function cors(resp) {
  const h = new Headers(resp.headers);
  h.set("Access-Control-Allow-Origin", "*");
  h.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  h.set("Access-Control-Allow-Headers", "Content-Type, Authorization");
  return new Response(resp.body, { status: resp.status, statusText: resp.statusText, headers: h });
}
