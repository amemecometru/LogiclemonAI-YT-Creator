export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type, Authorization' }
      });
    }

    if (request.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'Method not allowed' }), { status: 405, headers: { 'Content-Type': 'application/json' } });
    }

    const auth = request.headers.get('Authorization');
    if (!env.API_TOKEN) {
      return new Response(JSON.stringify({ error: 'Server misconfigured: API_TOKEN is not set' }), { status: 500, headers: { 'Content-Type': 'application/json' } });
    }
    if (auth !== `Bearer ${env.API_TOKEN}`) {
      return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401, headers: { 'Content-Type': 'application/json' } });
    }

    try {
      const body = await request.json();
      const topic = body.topic || '';
      const maxResults = Math.min(body.max_results || 5, 10);

      if (!topic) {
        return new Response(JSON.stringify({ error: 'topic is required' }), { status: 400, headers: { 'Content-Type': 'application/json' } });
      }

      const results = await searchWeb(topic, maxResults);
      const scraped = await scrapeResults(results);

      return new Response(JSON.stringify({ status: 'success', results: scraped, source: 'cloudflare-research' }), {
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
      });
    } catch (err) {
      return new Response(JSON.stringify({ status: 'error', message: err.message }), {
        status: 500, headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
      });
    }
  }
};

async function searchWeb(topic, maxResults) {
  const resp = await fetch('https://lite.duckduckgo.com/lite/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'User-Agent': 'Mozilla/5.0 (compatible; LogiclemonAI/1.0)'
    },
    body: `q=${encodeURIComponent(topic)}`
  });
  const html = await resp.text();

  const results = [];
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

  for (let i = 0; i < Math.min(links.length, maxResults); i++) {
    results.push({
      title: links[i].title,
      url: links[i].href.startsWith('http') ? links[i].href : `https://${links[i].href}`,
      snippet: snippets[i] || '',
      source: 'DuckDuckGo'
    });
  }

  return results;
}

async function scrapeResults(results) {
  const out = [];
  for (const r of results) {
    try {
      const resp = await fetch(r.url, {
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
        signal: AbortSignal.timeout(5000)
      });
      const html = await resp.text();
      const text = extractText(html).substring(0, 3000);
      out.push({
        title: r.title,
        url: r.url,
        content: text,
        snippet: r.snippet,
        credibility_score: 0.7
      });
    } catch {
      out.push({
        title: r.title,
        url: r.url,
        content: r.snippet,
        snippet: r.snippet,
        credibility_score: 0.5
      });
    }
  }
  return out;
}

function extractText(html) {
  let text = html
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&[^;]+;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return text.substring(0, 3000);
}

function stripHtml(html) {
  return html.replace(/<[^>]+>/g, '').replace(/&[^;]+;/g, ' ').replace(/\s+/g, ' ').trim();
}
