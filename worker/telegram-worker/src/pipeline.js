// Pipeline steps — each <30s, chained via self-fetch
// Prompts stay in English (quality-controlled) with language instruction for output

const LANGS = {
  en: 'English', hi: 'Hindi', ru: 'Russian',
  id: 'Indonesian', tr: 'Turkish', pt: 'Portuguese',
};

const TIER = {
  standard: { text: 'openrouter/free', image: 'google/gemini-2.5-flash-image', stars: 10, label: 'Standard' },
  pro:      { text: 'google/gemma-4-26b-a4b-it', image: 'google/gemini-3.1-flash-image-preview', stars: 25, label: 'Pro' },
  premium:  { text: 'google/gemini-3.1-pro-preview', image: 'google/gemini-3-pro-image', stars: 60, label: 'Premium' },
};

function langInstruct(lang) {
  if (lang === 'en') return '';
  return `\n\nIMPORTANT: Write ALL output in ${LANGS[lang] || lang}. The title, hook, sections, everything must be in ${LANGS[lang] || lang}.`;
}

export async function pipelineStep(task, step, env) {
  switch (step) {
    case 1: return await stepResearch(task, env);
    case 2: return await stepScriptElements(task, env);
    case 3: return await stepScriptSections(task, env);
    case 4: return await stepSeo(task, env);
    case 5: return await stepThumbnailDesign(task, env);
    case 6: return await stepThumbnailImage(task, env);
    case 7: return await stepSave(task, env);
    default:
      task.status = 'error';
      task.error = 'Unknown step: ' + step;
      return task;
  }
}

function getModel(tier, type) {
  const cfg = TIER[tier] || TIER.standard;
  return cfg[type] || TIER.standard[type];
}

async function callOpenRouter(messages, env, maxTokens = 1000, temp = 0.7, model) {
  const resp = await fetch(`${env.OPENROUTER_BASE}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${env.OPENROUTER_API_KEY}`,
    },
    body: JSON.stringify({
      model: model || 'openrouter/free',
      messages,
      max_tokens: maxTokens,
      temperature: temp,
    }),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`OpenRouter ${resp.status}: ${err}`);
  }
  const data = await resp.json();
  const content = data.choices?.[0]?.message?.content || '';
  // Strip markdown code fences if present
  let cleaned = content.trim();
  if (cleaned.startsWith('```')) {
    cleaned = cleaned.replace(/^```(\w+)?\\n?/, '').replace(/\\n?```$/, '').trim();
  }
  return cleaned;
}

async function callOpenRouterJSON(messages, env, maxTokens = 1500, temp = 0.7) {
  const text = await callOpenRouter(messages, env, maxTokens, temp);
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`LLM returned invalid JSON: ${text.slice(0, 200)}`);
  }
}

// ── Step 1: Research ──────────────────────────────────────────
async function stepResearch(task, env) {
  const resp = await fetch(`${env.RESEARCH_WORKER_URL}/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${env.RESEARCH_TOKEN}`,
    },
    body: JSON.stringify({ topic: task.topic, max_results: 5 }),
  });
  const data = await resp.json();
  task.research = data.results || [];
  task.step = 1;
  return task;
}

// ── Step 2: Script elements (title + hook + conclusion + CTA) ──
async function stepScriptElements(task, env) {
  const findings = (task.research || []).slice(0, 3).map(r => `- ${r.title || r.snippet || ''}`).join('\\n');

  const prompt = `Generate the title, hook, conclusion, and call-to-action for a YouTube video about "${task.topic}" for ${task.audience || 'general audience'}.${langInstruct(task.lang)}

Research context:
${findings || 'No specific research available.'}

Requirements:
- Title: 30-60 characters, clickable, SEO-friendly, power words
- Hook: 30-40 words, starts with a pattern interrupt (question or bold statement), creates curiosity gap
- Conclusion: ~60 words, summarizes key takeaway, reinforces the main message
- Call-to-action: ~50 words, ask for like/subscribe/comment, mention next video topic

Return as JSON only:
{
  "title": "...",
  "hook": "...",
  "conclusion": "...",
  "call_to_action": "..."
}`;

  const result = await callOpenRouterJSON([{ role: 'user', content: prompt }], env, 600, 0.8);
  task.title = result.title || task.topic;
  task.hook = result.hook || '';
  task.conclusion = result.conclusion || '';
  task.cta = result.call_to_action || '';
  task.step = 2;
  return task;
}

// ── Step 3: Script sections ────────────────────────────────────
async function stepScriptSections(task, env) {
  const numSections = 4;
  const findings = (task.research || []).slice(0, 5).map(r => `- ${r.title || r.snippet || ''}`).join('\\n');

  const prompt = `Create a structured outline for a YouTube video about "${task.topic}" with ${numSections} sections.${langInstruct(task.lang)}

Target audience: ${task.audience || 'general'}
Tone: conversational
Each section: ~90 seconds

Research findings:
${findings || 'No specific research available.'}

Return JSON array:
[
  {
    "title": "Section title",
    "content": "What to say in this section (~180 words)",
    "visual_cue": "what to show on screen"
  }
]

Return ONLY valid JSON array.`;

  const raw = await callOpenRouterJSON([{ role: 'user', content: prompt }], env, 2000, 0.7);

  const sections = (Array.isArray(raw) ? raw : []).slice(0, numSections).map((s, i) => ({
    title: s.title || `Section ${i + 1}`,
    content: s.content || '',
    visual_cue: s.visual_cue || '',
    timestamp: `${Math.floor(i * 90 / 60)}:${String((i * 90) % 60).padStart(2, '0')}`,
  }));

  task.sections = sections;
  task.word_count = sections.reduce((sum, s) => sum + (s.content || '').split(' ').length, 0);
  task.step = 3;
  return task;
}

// ── Step 4: SEO (title variants + tags + description) ──────────
async function stepSeo(task, env) {
  const sections = (task.sections || []).map(s => `- ${s.title}`).join('\\n');

  // Title variants
  const titlePrompt = `Generate 5 SEO-optimized title variants for a YouTube video about "${task.topic}".${langInstruct(task.lang)}

Current title: ${task.title || task.topic}

Rules:
- Each 30-60 characters
- Include a power word or number
- Create curiosity gap
- Different angle/approach each

Return as JSON:
{
  "variants": ["variant 1", "variant 2", "variant 3", "variant 4", "variant 5"]
}`;

  const titleData = await callOpenRouterJSON([{ role: 'user', content: titlePrompt }], env, 500, 0.7);
  task.title_variants = (titleData.variants || []).slice(0, 5);

  // Tags + description
  const metaPrompt = `Generate YouTube tags and a video description for "${task.topic}" targeted at ${task.audience || 'general'}.${langInstruct(task.lang)}

Hook: ${(task.hook || '').slice(0, 100)}
Sections:
${sections || '- Introduction'}

Tags rules:
- 15-20 tags, mix of broad and specific
- Include common variations
- Return as JSON array

Description rules:
- First 2 lines must hook the viewer (shows in search results)
- 150-300 words, paragraph breaks
- Include relevant hashtags at the end

Return as JSON:
{
  "tags": ["tag1", "tag2", ...],
  "description": "..."
}`;

  const metaData = await callOpenRouterJSON([{ role: 'user', content: metaPrompt }], env, 800, 0.7);
  task.tags = (metaData.tags || []).slice(0, 20);
  task.description = metaData.description || '';
  task.step = 4;
  return task;
}

// ── Step 5: Thumbnail design (concept + composition + text) ────
async function stepThumbnailDesign(task, env) {
  const prompt = `Create a YouTube thumbnail design for a video titled "${task.title || task.topic}" about ${task.topic}.${langInstruct(task.lang)}

Emotions to convey: curiosity, surprise, urgency

Provide three things as JSON:
{
  "concept": "3-4 sentence concept: main focal point, background, people/expressions, visual hook",
  "composition": "3-5 sentence guide: layout, focal point, text placement, lighting",
  "text_overlay": "MAX 3 punchy words, creates curiosity"
}`;

  const result = await callOpenRouterJSON([{ role: 'user', content: prompt }], env, 600, 0.7);
  task.thumb_concept = result.concept || '';
  task.thumb_composition = result.composition || '';
  task.thumb_text = result.text_overlay || '';
  task.step = 5;
  return task;
}

// ── Step 6: Thumbnail image (via Nano Banana) ──────────────────
async function stepThumbnailImage(task, env) {
  const genPrompt = `Create a YouTube thumbnail. Concept: ${task.thumb_concept || ''} Composition: ${task.thumb_composition || ''} Text overlay: '${task.thumb_text || ''}' in bold white font with black stroke. Style: high contrast, 1280x720.`;

  const resp = await fetch(`${env.OPENROUTER_BASE}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${env.OPENROUTER_API_KEY}`,
    },
    body: JSON.stringify({
      model: 'google/gemini-2.5-flash-image',
      messages: [{ role: 'user', content: [{ type: 'text', text: genPrompt }] }],
      modalities: ['image', 'text'],
    }),
  });
  if (!resp.ok) {
    task.thumbnail_url = '';
    task.step = 6;
    return task;
  }
  const data = await resp.json();
  const msg = data.choices?.[0]?.message || {};
  const images = msg.images;
  let imageUrl = '';

  if (images?.[0]?.image_url?.url) {
    imageUrl = images[0].image_url.url;
  } else {
    const content = msg.content || '';
    const urlMatch = content.match(/https?:\/\/[^\s)'"]+/);
    imageUrl = urlMatch ? urlMatch[0] : '';
  }

  // Save image to R2 if available
  if (imageUrl && imageUrl.startsWith('data:image') && env.R2) {
    const b64 = imageUrl.split(',')[1];
    const buf = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const key = `thumbnails/${task.id}.png`;
    await env.R2.put(key, buf, { httpMetadata: { contentType: 'image/png' } });
    task.thumbnail_url = `/api/thumbnails/${task.id}.png`;
  } else if (imageUrl) {
    task.thumbnail_url = imageUrl;
  } else {
    task.thumbnail_url = '';
  }

  task.step = 6;
  return task;
}

// ── Step 7: Save to D1 ─────────────────────────────────────────
async function stepSave(task, env) {
  const record = {
    id: task.id,
    topic: task.topic,
    title: task.title || task.topic,
    lang: task.lang || 'en',
    tg_user: task.tg_user || '',
    status: 'completed',
    result: JSON.stringify({
      title: task.title,
      hook: task.hook,
      sections: task.sections,
      conclusion: task.conclusion,
      cta: task.cta,
      word_count: task.word_count,
      tags: task.tags,
      description: task.description,
      title_variants: task.title_variants,
      thumbnail_url: task.thumbnail_url || '',
      thumb_concept: task.thumb_concept,
      thumb_text: task.thumb_text,
    }),
    created_at: task.created_at || Date.now(),
  };

  try {
    await fetch(`${env.DB_WORKER_URL}/db/yt_videos`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${env.DB_TOKEN}`,
      },
      body: JSON.stringify(record),
    });
  } catch (e) {
    // Non-fatal — task still completed
    console.error('Save failed:', e.message);
  }

  task.status = 'completed';
  task.step = 7;
  return task;
}
