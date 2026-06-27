// Pipeline steps — each <30s, chained via self-fetch
// Prompts stay in English (quality-controlled) with language instruction for output

const LANGS = {
  en: 'English', hi: 'Hindi', ru: 'Russian',
  id: 'Indonesian', tr: 'Turkish', pt: 'Portuguese',
};

const TIER = {
  standard: { text: 'openrouter/free', image: 'google/gemini-2.5-flash-image', label: 'Standard' },
  pro:      { text: 'google/gemma-4-26b-a4b-it', image: 'google/gemini-3.1-flash-image-preview', label: 'Pro' },
  premium:  { text: 'google/gemini-3.1-pro-preview', image: 'google/gemini-3-pro-image', label: 'Premium' },
};

// Emerging currency markets configured for automatic cost-degradation
const EMERGING_LOCALES = ['pt', 'ru', 'hi', 'id', 'tr', 'br', 'in', 'ru-ru', 'hi-in'];

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

// ── REGIONAL ARBITRAGE MODEL INTERCEPTOR ──
function getModel(tier, type, locale = 'en') {
  let targetTier = tier || 'standard';
  const userLocale = (locale || 'en').toLowerCase();

  // If they want Premium but live in a Tier 2/3 region, seamlessly route to high-speed Pro/Flash clusters
  if (targetTier === 'premium' && EMERGING_LOCALES.includes(userLocale)) {
    console.log(`[Arbitrage Engine] Regional mitigation triggered for locale: ${userLocale}. Rerouting text/image layers.`);
    targetTier = 'pro'; 
  }

  const cfg = TIER[targetTier] || TIER.standard;
  return cfg[type] || TIER.standard[type];
}

async function callOpenRouter(messages, env, maxTokens = 1000, temp = 0.7, model) {
  const targetModel = model || 'openrouter/free';
  
  const resp = await fetch(`${env.OPENROUTER_BASE}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${env.OPENROUTER_API_KEY}`,
    },
    body: JSON.stringify({
      model: targetModel,
      messages,
      max_tokens: maxTokens,
      temperature: temp,
    }),
  });
  
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`OpenRouter Core Error (${resp.status}): ${err}`);
  }
  
  const data = await resp.json();
  const content = data.choices?.[0]?.message?.content || '';
  
  let cleaned = content.trim();
  if (cleaned.startsWith('```')) {
    cleaned = cleaned.replace(/^```(json)?\s*/i, '').replace(/\s*```$/, '').trim();
  }
  return cleaned;
}

async function callOpenRouterJSON(messages, env, maxTokens = 1500, temp = 0.7, model) {
  const text = await callOpenRouter(messages, env, maxTokens, temp, model);
  try {
    return JSON.parse(text);
  } catch (err) {
    throw new Error(`LLM Payload JSON Parsing Failure. Output snapshot: ${text.slice(0, 150)}`);
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
  const findings = (task.research || []).slice(0, 3).map(r => `- ${r.title || r.snippet || ''}`).join('\n');
  const targetModel = getModel(task.tier, 'text', task.locale);

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

  const result = await callOpenRouterJSON([{ role: 'user', content: prompt }], env, 600, 0.8, targetModel);
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
  const findings = (task.research || []).slice(0, 5).map(r => `- ${r.title || r.snippet || ''}`).join('\n');
  const targetModel = getModel(task.tier, 'text', task.locale);

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

  const raw = await callOpenRouterJSON([{ role: 'user', content: prompt }], env, 2000, 0.7, targetModel);

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

// ── Step 4: SEO ───────────────────────────────────────────────
async function stepSeo(task, env) {
  const sections = (task.sections || []).map(s => `- ${s.title}`).join('\n');
  const targetModel = getModel(task.tier, 'text', task.locale);

  const titlePrompt = `Generate 5 SEO-optimized title variants for a YouTube video about "${task.topic}".${langInstruct(task.lang)}

Current title: ${task.title || task.topic}

Return as JSON:
{
  "variants": ["variant 1", "variant 2", "variant 3", "variant 4", "variant 5"]
}`;

  const titleData = await callOpenRouterJSON([{ role: 'user', content: titlePrompt }], env, 500, 0.7, targetModel);
  task.title_variants = (titleData.variants || []).slice(0, 5);

  const metaPrompt = `Generate YouTube tags and a video description for "${task.topic}" targeted at ${task.audience || 'general'}.${langInstruct(task.lang)}

Hook: ${(task.hook || '').slice(0, 100)}
Sections:
${sections || '- Introduction'}

Return as JSON:
{
  "tags": ["tag1", "tag2", ...],
  "description": "..."
}`;

  const metaData = await callOpenRouterJSON([{ role: 'user', content: metaPrompt }], env, 800, 0.7, targetModel);
  task.tags = (metaData.tags || []).slice(0, 20);
  task.description = metaData.description || '';
  task.step = 4;
  return task;
}

// ── Step 5: Thumbnail design ──────────────────────────────────
async function stepThumbnailDesign(task, env) {
  const targetModel = getModel(task.tier, 'text', task.locale);
  const prompt = `Create a YouTube thumbnail design for a video titled "${task.title || task.topic}" about ${task.topic}.${langInstruct(task.lang)}

Provide three things as JSON:
{
  "concept": "3-4 sentence concept",
  "composition": "3-5 sentence guide",
  "text_overlay": "MAX 3 punchy words"
}`;

  const result = await callOpenRouterJSON([{ role: 'user', content: prompt }], env, 600, 0.7, targetModel);
  task.thumb_concept = result.concept || '';
  task.thumb_composition = result.composition || '';
  task.thumb_text = result.text_overlay || '';
  task.step = 5;
  return task;
}

// ── Step 6: Thumbnail image ───────────────────────────────────
async function stepThumbnailImage(task, env) {
  const genPrompt = `Create a YouTube thumbnail. Concept: ${task.thumb_concept || ''} Composition: ${task.thumb_composition || ''} Text overlay: '${task.thumb_text || ''}' in bold white font with black stroke. Style: high contrast, 1280x720. CRITICAL: Keep ALL text at least 8% (102px) inside all edges — no text in the outer 8% margin zone.`;
  const imageModel = getModel(task.tier, 'image', task.locale);

  const resp = await fetch(`${env.OPENROUTER_BASE}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${env.OPENROUTER_API_KEY}`,
    },
    body: JSON.stringify({
      model: imageModel,
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

  task.thumbnail_url = imageUrl || '';
  task.step = 6;
  return task;
}

// ── Step 7: Save Directly to Bound D1 ──────────────────────────
async function stepSave(task, env) {
  const payloadResult = {
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
  };

  try {
    await env.DB.prepare(`
      INSERT INTO users_videos (id, telegram_id, topic, title, language, status, result_payload, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(
      task.id,
      task.tg_user || 'anon',
      task.topic,
      task.title || task.topic,
      task.lang || 'en',
      'completed',
      JSON.stringify(payloadResult),
      task.created_at || Date.now()
    ).run();
  } catch (e) {
    console.error('D1 Writing Exception:', e.message);
  }

  task.status = 'completed';
  task.step = 7;
  return task;
}
