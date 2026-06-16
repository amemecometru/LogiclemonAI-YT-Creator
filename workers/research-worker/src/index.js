export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return cors(new Response(null, { status: 204 }));
    if (request.method !== 'POST') return cors(json({ error: 'Method not allowed' }, 405));

    const auth = request.headers.get('Authorization');
    if (!env.API_TOKEN) return cors(json({ error: 'Server misconfigured: API_TOKEN is not set' }, 500));
    if (auth !== `Bearer ${env.API_TOKEN}`) return cors(json({ error: 'Unauthorized' }, 401));

    try {
      const body = await request.json().catch(() => ({}));
      const topic = (body.topic || '').trim();
      const maxResults = Math.min(parseInt(body.max_results || 5, 10) || 5, 10);
      if (!topic) return cors(json({ error: 'topic is required' }, 400));

      const cacheKey = `r:${maxResults}:${topic.toLowerCase()}`;

      // Optional KV cache — bind RESEARCH_CACHE to enable; the worker runs fine without it.
      if (env.RESEARCH_CACHE) {
        const hit = await env.RESEARCH_CACHE.get(cacheKey, 'json').catch(() => null);
        if (hit) return cors(json({ status: 'success', results: hit, source: 'cache' }));
      }

      const links = await searchWeb(topic, maxResults);
      const scraped = await scrapeResults(links);

      if (env.RESEARCH_CACHE && scraped.length) {
        // 6h TTL; never fail the request if the cache write errors.
        await env.RESEARCH_CACHE.put(cacheKey, JSON.stringify(scraped), { expirationTtl: 21600 }).catch(() => {});
      }
      return cors(json({ status: 'success', results: scraped, source: 'cloudflare-research' }));
    } catch (err) {
      return cors(json({ status: 'error', message: String((err && err.message) || err) }, 500));
    }
  },
};

async function searchWeb(topic, maxResults) {
  let html = '';
  try {
    const resp = await fetch('https://lite.duckduckgo.com/lite/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'Mozilla/5.0 (compatible; LogiclemonAI/1.0)' },
      body: `q=${encodeURIComponent(topic)}`,
      signal: AbortSignal.timeout(8000),
    });
    if (!resp.ok) return [];          // DDG rate-limit / error — degrade to no sources
    html = await resp.text();
  } catch {
    return [];
  }

  const linkRegex = /<a[^>]+href=(["'])([^"']+)\1[^>]*class=(["'])result-link\3[^>]*>([\s\S]*?)<\/a>/gi;
  const snippetRegex = /<td[^>]*class=(["'])result-snippet\1[^>]*>([\s\S]*?)<\/td>/gi;

  const links = [];
  let m;
  while ((m = linkRegex.exec(html)) !== null && links.length < maxResults) {
    links.push({ href: m[2], title: stripHtml(m[4]).trim() });
  }
  const snippets = [];
  while ((m = snippetRegex.exec(html)) !== null && snippets.length < maxResults) {
    snippets.push(stripHtml(m[2]).trim());
  }

  const results = [];
  for (let i = 0; i < Math.min(links.length, maxResults); i++) {
    results.push({
      title: links[i].title,
      url: links[i].href.startsWith('http') ? links[i].href : `https://${links[i].href}`,
      snippet: snippets[i] || '',
      source: 'DuckDuckGo',
    });
  }
  return results;
}

async function scrapeResults(results) {
  // Fetch result pages concurrently; each has its own timeout and falls back to the snippet.
  return Promise.all(results.map(async (r) => {
    try {
      const resp = await fetch(r.url, {
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
        signal: AbortSignal.timeout(5000),
      });
      if (!resp.ok) throw new Error('non-200');
      const html = await resp.text();
      return { title: r.title, url: r.url, content: extractText(html), snippet: r.snippet, credibility_score: 0.7 };
    } catch {
      return { title: r.title, url: r.url, content: r.snippet, snippet: r.snippet, credibility_score: 0.5 };
    }
  }));
}

function extractText(html) {
  return html
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&[^;]+;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .substring(0, 3000);
}

function stripHtml(html) {
  return html.replace(/<[^>]+>/g, '').replace(/&[^;]+;/g, ' ').replace(/\s+/g, ' ').trim();
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });
}

function cors(resp) {
  const h = new Headers(resp.headers);
  h.set('Access-Control-Allow-Origin', '*');
  h.set('Access-Control-Allow-Methods', 'POST, OPTIONS');
  h.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  return new Response(resp.body, { status: resp.status, statusText: resp.statusText, headers: h });
}
