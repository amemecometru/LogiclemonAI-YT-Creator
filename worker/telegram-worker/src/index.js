import { pipelineStep } from './pipeline.js';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    const origin = request.headers.get('Origin') || '*';

    const cors = (body, status = 200) => new Response(JSON.stringify(body), {
      status, headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      }
    });

    if (request.method === 'OPTIONS') return cors({});

    // Serve mini-app HTML
    if (path === '/' && request.method === 'GET') {
      const html = await getMiniAppHtml(env);
      return new Response(html, {
        headers: { 
          'Content-Type': 'text/html; charset=utf-8', 
          'Access-Control-Allow-Origin': '*', 
          'Cache-Control': 'no-cache, no-store, must-revalidate', 
          'Pragma': 'no-cache', 
          'Expires': '0' 
        }
      });
    }

    // ── R2 STORAGE IMAGE SERVING ROUTE ──
    if (path.startsWith('/api/thumbnails/') && request.method === 'GET') {
      const id = path.split('/').pop().replace('.png', '');
      if (env.R2) {
        const object = await env.R2.get(`thumbnails/${id}.png`);
        if (object) {
          const headers = new Headers();
          object.writeHttpMetadata(headers);
          headers.set('Access-Control-Allow-Origin', '*');
          return new Response(object.body, { headers });
        }
      }
      return new Response('Asset not compiled or R2 unlinked', { status: 404 });
    }

    // ── PIPELINE ROUTE A: PIPELINE KICKOFF ──
    if (path === '/api/pipeline/start' && request.method === 'POST') {
      const { topic, lang = 'en', tier = 'standard', audience = 'general', tg_user = 'anon' } = await request.json();
      if (!topic) return cors({ error: 'Creation topic required to start pipeline' }, 400);

      const taskId = crypto.randomUUID();
      const task = {
        id: taskId,
        topic,
        lang,
        tier,
        audience,
        tg_user,
        step: 0,
        status: 'processing',
        created_at: Date.now()
      };

      // Write initial state to KV tracking
      await env.TASKS.put('task:status:' + taskId, JSON.stringify(task), { expirationTtl: 86400 });

      // Fire asynchronous background self-fetch step execution
      ctx.waitUntil(
        fetch(`https://${url.host}/api/pipeline/step`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ taskId, step: 1 })
        }).catch(err => console.error("Pipeline kick-off step fire dropped:", err.message))
      );

      return cors({ success: true, taskId });
    }

    // ── PIPELINE ROUTE B: PIPELINE CHAINED STEP PROGRESSOR ──
    if (path === '/api/pipeline/step' && request.method === 'POST') {
      const { taskId, step } = await request.json();
      if (!taskId || !step) return cors({ error: 'Missing step tracking variables' }, 400);

      const raw = await env.TASKS.get('task:status:' + taskId);
      if (!raw) return cors({ error: 'Telemetry task ID not found in KV registry' }, 404);
      let task = JSON.parse(raw);

      try {
        task.status = 'processing';
        // Run single segmented pipeline computation phase
        task = await pipelineStep(task, step, env);
        await env.TASKS.put('task:status:' + taskId, JSON.stringify(task), { expirationTtl: 86400 });

        // Trigger next sequential self-fetch if step is below closure boundaries
        if (task.status !== 'error' && step < 7) {
          ctx.waitUntil(
            fetch(`https://${url.host}/api/pipeline/step`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ taskId, step: step + 1 })
            }).catch(err => console.error(`Step progression context drop at step ${step}:`, err.message))
          );
        }
        return cors({ success: true, currentStep: step });
      } catch (err) {
        task.status = 'error';
        task.error = err.message;
        await env.TASKS.put('task:status:' + taskId, JSON.stringify(task), { expirationTtl: 86400 });
        return cors({ error: 'Pipeline process exception points triggered', detail: err.message }, 500);
      }
    }

    // ── PIPELINE ROUTE C: LIVE TELEMETRY STATE POLLER ──
    if (path === '/api/pipeline/status' && request.method === 'GET') {
      const taskId = url.searchParams.get('taskId');
      if (!taskId) return cors({ error: 'Task lookup token required' }, 400);

      const raw = await env.TASKS.get('task:status:' + taskId);
      if (!raw) return cors({ error: 'No active telemetry found' }, 404);
      return cors(JSON.parse(raw));
    }

    // ── NATIVE OAUTH ROUTE A: INITIATE GOOGLE REDIRECT ──
    if (path === '/api/auth/google' && request.method === 'GET') {
      const tgUser = url.searchParams.get('tg_user') || 'anon';
      const redirectUri = `https://${url.host}/api/auth/callback`;
      
      const googleAuthUrl = `https://accounts.google.com/o/oauth2/v2/auth?` + 
        `client_id=${env.GOOGLE_CLIENT_ID}` +
        `&redirect_uri=${encodeURIComponent(redirectUri)}` +
        `&response_type=code` +
        `&scope=${encodeURIComponent('openid email profile')}` +
        `&state=${encodeURIComponent(tgUser)}`;
        
      return Response.redirect(googleAuthUrl, 302);
    }

    // ── NATIVE OAUTH ROUTE B: OAUTH CALLBACK INTERCEPTOR ──
    if (path === '/api/auth/callback' && request.method === 'GET') {
      const code = url.searchParams.get('code');
      const tgUser = url.searchParams.get('state') || 'anon';
      const redirectUri = `https://${url.host}/api/auth/callback`;

      if (!code) return cors({ error: 'OAuth authorization code missing from upstream' }, 400);

      try {
        const tokenResp = await fetch('https://oauth2.googleapis.com/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({
            code,
            client_id: env.GOOGLE_CLIENT_ID,
            client_secret: env.GOOGLE_CLIENT_SECRET,
            redirect_uri: redirectUri,
            grant_type: 'authorization_code',
          }),
        });

        const tokens = await tokenResp.json();
        if (tokens.error) throw new Error(`Google Token Fault: ${tokens.error_description}`);

        const userResp = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
          headers: { Authorization: `Bearer ${tokens.access_token}` },
        });
        const profile = await userResp.json();

        if (!profile.email) throw new Error('Failed to isolate a valid email signature.');

        const timestamp = Date.now();
        await env.DB.prepare(`
          INSERT INTO users (telegram_id, email, google_id, created_at, updated_at)
          VALUES (?, ?, ?, ?, ?)
          ON CONFLICT(telegram_id) DO UPDATE SET
            email = excluded.email,
            google_id = excluded.google_id,
            updated_at = excluded.updated_at
        `).bind(tgUser, profile.email, profile.id, timestamp, timestamp).run();

        return Response.redirect(`https://${url.host}/?auth=success&tg_user=${tgUser}`, 302);
      } catch (err) {
        return new Response(`Identity Verification Failed: ${err.message}`, { status: 500 });
      }
    }

    // ── ENDPOINT 1: ASSISTANT CHAT QUEUE ──
    if (path === '/api/chat' && request.method === 'POST') {
      const { message, history = [] } = await request.json();
      if (!message) return cors({ error: 'Message payload empty' }, 400);

      const systemPrompt = "You are the Logiclemon Studio Assistant. You engineer high-impact short-form scripts (YouTube Shorts, TikToks), draft punchy social threads, and write exceptionally detailed visual prompts for advanced image creation systems like FLUX and DALL-E.";

      try {
        const resp = await fetch(`${env.OPENROUTER_BASE}/chat/completions`, {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json', 
            'Authorization': 'Bearer ' + env.OPENROUTER_API_KEY 
          },
          body: JSON.stringify({
            model: 'google/gemini-2.5-flash',
            messages: [{ role: 'system', content: systemPrompt }, ...history, { role: 'user', content: message }]
          })
        });

        if (!resp.ok) {
          const errBody = await resp.text();
          return cors({ error: `OpenRouter Connection Rejected (${resp.status})`, detail: errBody }, resp.status);
        }

        const data = await resp.json();
        return cors({ reply: data.choices?.[0]?.message?.content || 'Model responded with empty message structure.' });
      } catch (err) {
        return cors({ error: 'Assistant pipeline error', detail: err.message }, 500);
      }
    }

    // ── ENDPOINT 2: STANDALONE DIRECT IMAGE LAB ──
    if (path === '/api/generate-image' && request.method === 'POST') {
      const { prompt, model, tg_user } = await request.json();
      if (!prompt) return cors({ error: 'Visual prompt description is required' }, 400);

      try {
        const targetModel = model || 'bfl/flux-2-pro-preview';
        const imageAsset = await generateDirectImage(prompt, targetModel, env);

        const taskId = crypto.randomUUID();
        const record = { id: taskId, title: prompt.substring(0, 30) + '...', created_at: Date.now(), tg_user: tg_user || 'anon', status: 'completed' };
        await env.TASKS.put('history:' + taskId + ':' + (tg_user || 'anon'), JSON.stringify(record), { expirationTtl: 86400 });

        return cors({ image_url: imageAsset.url, provider: imageAsset.provider });
      } catch (err) {
        return cors({ error: 'Direct creation processing hit an exception point', detail: err.message }, 500);
      }
    }

    // ── ENDPOINT 3: AUTOMATED SOCIAL TEXT MACHINE ──
    if (path === '/api/social/create' && request.method === 'POST') {
      const { topic, platform } = await request.json();
      if (!topic) return cors({ error: 'Content topic required' }, 400);

      const targetPrompt = platform === 'shorts'
        ? `Write a 60-second viral YouTube Shorts script about "${topic}". Use an explosive 3-second hook, visual screen directions, conversational narrative flow, and an aggressive subscription CTA.`
        : `Write a high-retention, value-packed 4-post micro-thread for social media posts about "${topic}". Optimize layout spacing, keep it crisp, clean, and omit hashtags completely.`;

      try {
        const resp = await fetch(`${env.OPENROUTER_BASE}/chat/completions`, {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json', 
            'Authorization': 'Bearer ' + env.OPENROUTER_API_KEY 
          },
          body: JSON.stringify({
            model: 'google/gemini-2.5-flash',
            messages: [{ role: 'user', content: targetPrompt }]
          })
        });

        if (!resp.ok) {
          const errBody = await resp.text();
          return cors({ error: `Social Mesh Rejected Query (${resp.status})`, detail: errBody }, resp.status);
        }

        const data = await resp.json();
        return cors({ result: data.choices?.[0]?.message?.content || 'Model responded with blank data.' });
      } catch (err) {
        return cors({ error: 'Social composer dropped connectivity', detail: err.message }, 500);
      }
    }

    // ── ENDPOINT 4: HISTORICAL METRIC LOGS (D1 DIRECT READ OPTIMIZATION) ──
    if (path === '/api/history' && request.method === 'GET') {
      const tgUser = url.searchParams.get('tg_user');
      if (!tgUser) return cors({ error: 'Valid uid required' }, 400);
      
      try {
        const { results } = await env.DB.prepare(`
          SELECT * FROM users_videos WHERE telegram_id = ? ORDER BY created_at DESC
        `).bind(tgUser).all();

        const items = results.map(row => ({
          id: row.id,
          title: row.title,
          topic: row.topic,
          lang: row.language,
          status: row.status,
          created_at: row.created_at,
          result: row.result_payload ? JSON.parse(row.result_payload) : null
        }));

        return cors({ items });
      } catch (err) {
        return cors({ error: 'Database execution failure', detail: err.message }, 500);
      }
    }

    return cors({ error: 'Route not mapped on edge mesh' }, 404);
  }
};

async function generateDirectImage(prompt, modelId, env) {
  if (modelId.startsWith('bfl/') || modelId.includes('flux')) {
    const bflEngine = modelId.replace('bfl/', '') || 'flux-2-pro-preview';
    const submitResp = await fetch(`https://api.bfl.ai/v1/${bflEngine}`, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'x-key': env.BFL_API_KEY
      },
      body: JSON.stringify({ prompt: prompt, width: 1024, height: 1024, prompt_upsampling: true, output_format: 'png' })
    });
    if (!submitResp.ok) throw new Error(`BFL Access Fault: ${await submitResp.text()}`);
    
    const submission = await submitResp.json();
    const pollingUrl = submission.polling_url;
    if (!pollingUrl) throw new Error('BFL execution block failed to return trackable state variables.');

    let attempts = 0;
    while (attempts < 20) {
      await new Promise(res => setTimeout(res, 2500));
      const statusResp = await fetch(pollingUrl, { method: 'GET', headers: { 'x-key': env.BFL_API_KEY } });
      if (!statusResp.ok) throw new Error('BFL status check lost data sync links.');
      const statusData = await statusResp.json();
      if (statusData.status === 'Ready') return { url: statusData.result?.sample || '', provider: 'Black Forest Labs (FLUX)' };
      if (statusData.status === 'Failed') throw new Error('Upstream FLUX hardware cluster threw a prompt generation failure anomaly.');
      attempts++;
    }
    throw new Error('BFL processing loop context timed out across boundary gates.');
  }

  if (modelId.startsWith('openai/') || modelId.includes('gpt-image') || modelId.includes('dall-e')) {
    const openAIModel = modelId.replace('openai/', '') || 'gpt-image-2';
    const resp = await fetch('https://api.openai.com/v1/images/generations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + env.OPENAI_API_KEY },
      body: JSON.stringify({ model: openAIModel, prompt: prompt, n: 1, size: '1024x1024' })
    });
    if (!resp.ok) throw new Error(`OpenAI Access Fault: ${await resp.text()}`);
    const data = await resp.json();
    const targetUrl = data.data?.[0]?.url || '';
    if (!targetUrl) throw new Error('OpenAI vector payload output stream is blank.');
    return { url: targetUrl, provider: 'OpenAI (GPT Image)' };
  }

  if (modelId.startsWith('google/') || modelId.includes('imagen')) {
    const targetModel = 'imagen-3.0-generate-002';
    const resp = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${targetModel}:generateImages?key=${env.GOOGLE_AI_API_KEY}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ numberOfImages: 1, outputMimeType: 'image/png', aspectRatio: '1:1', prompt: { text: prompt } })
    });
    if (!resp.ok) throw new Error(`Google Imagen API Failure: ${await resp.text()}`);
    const data = await resp.json();
    const base64Data = data.generatedImages?.[0]?.image?.imageBytes;
    if (!base64Data) throw new Error('Google Imagen returned an empty visual image byte array.');
    return { url: `data:image/png;base64,${base64Data}`, provider: 'Google Imagen 3' };
  }

  throw new Error('Provider matching path missing handling conditions for token: ' + modelId);
}

function getMiniAppHtml(env) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>LogiclemonAI</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800;900&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">

  <style>
  :root{
    --bg-void:#04060a; --bg-base:#070b12; --bg-raise:#0b111b;
    --glazier-glass-1:rgba(22,39,61,.78); --glazier-glass-2:rgba(13,23,38,.72);
    --metal-hi:#eef2f6; --metal-1:#d4dbe3; --metal-2:#b9c2cc; --metal-4:#7e8a98;
    --teal:#3fe0d0; --teal-bright:#6bf0e3; --teal-soft:rgba(63,224,208,.45); --teal-faint:rgba(63,224,208,.14);
    --ember:#ff6a3d; --amber:#f6a93b;
    --ink-on-dark:#e6edf5; --ink-on-dark-dim:#9fb0c3; --ink-on-metal:#0a0e14;
    --line-dark:rgba(120,170,210,.16); --line-metal:rgba(255,255,255,.5);
    --blur-glass:blur(18px) saturate(140%);
    --shadow-card:0 24px 60px rgba(0,0,0,.55);
    --inset-glass:inset 0 1px 0 rgba(255,255,255,.08);
    --inset-metal:inset 0 1px 0 rgba(255,255,255,.85),inset 0 -1px 2px rgba(0,0,0,.28);
    --r-sm:8px; --r-md:14px; --r-lg:20px; --r-pill:999px;
    --font-ui:'Outfit',system-ui,-apple-system,sans-serif;
    --font-mono:'Space Mono',ui-monospace,'SF Mono',monospace;
    --ease:cubic-bezier(.22,.61,.36,1); --t-base:.3s;
    --app-height: 100%;
  }
  *,*::before,*::after{box-sizing:border-box; margin:0; padding:0;}
  html { scroll-behavior:smooth; height: 100%; background: var(--bg-void); }
  body { 
    background:var(--bg-void); color:var(--ink-on-dark); font-family:var(--font-ui); line-height:1.25;
    overflow-x:hidden; overflow-y:auto; -webkit-font-smoothing:antialiased;
    display: flex; justify-content: center; align-items: flex-start; min-height: 100vh;
  }
  .app-viewport { width: 100%; max-width: 480px; min-height: 100vh; background: var(--bg-base); position: relative; box-shadow: 0 0 60px rgba(0,0,0,0.8); border-left: 1px solid var(--line-dark); border-right: 1px solid var(--line-dark); display: flex; flex-direction: column; z-index: 1; }
  .bg{position:absolute;inset:0;z-index:0;pointer-events:none; background: radial-gradient(1100px 600px at 50% -10%,rgba(63,224,208,.10),transparent 60%), radial-gradient(900px 760px at 8% 112%,rgba(36,75,110,.30),transparent 60%), linear-gradient(180deg,var(--bg-base),var(--bg-void));}
  .wrap{position:relative;z-index:2; padding: 0 12px 24px; width: 100%;}
  .glz-surface-glass{position:relative; background:linear-gradient(160deg,var(--glazier-glass-1),var(--glazier-glass-2)); -webkit-backdrop-filter:var(--blur-glass); backdrop-filter:var(--blur-glass); border:1px solid var(--line-dark); border-radius:var(--r-lg); box-shadow:var(--inset-glass),var(--shadow-card); overflow: hidden;}
  .marquee{overflow:hidden; background:rgba(7,11,18,.55); padding:11px 0; position:relative; z-index:10; border-top:2px solid transparent; border-bottom:2px solid transparent; border-image:linear-gradient(90deg,transparent,var(--metal-4) 20%,#fff 50%,var(--metal-4) 80%,transparent) 1;}
  .marquee-track{display:flex; white-space:nowrap; width:max-content; animation:marquee 36s linear infinite;}
  .marquee-track > span{font-weight:600; font-size:14px; color:var(--ink-on-dark); padding:0 22px; text-transform:uppercase; letter-spacing:.05em; opacity: 0.8;}
  .yt-u{color: #ff3333; font-weight:800;}
  @keyframes marquee{to{transform:translateX(-50%);}}
  .brand-hero{padding:24px 4% 16px; text-align:center; position:relative;}
  .logo{font-weight:900; font-size:36px; line-height:1; letter-spacing:-.035em; color:var(--ink-on-dark);}
  .logo em{font-style:normal; color:var(--teal); text-shadow:0 0 24px var(--teal-soft);}
  .brand-hero .sub{font-family:var(--font-mono); font-size:9px; color:var(--teal); letter-spacing:.25em; text-transform:uppercase; margin-top:8px;}
  .landing-heading { font-weight: 800; font-size: 24px; color: var(--ink-on-dark); text-align: center; margin: 15px 0 5px; line-height: 1.2; }
  .landing-subhead { font-size: 13px; color: var(--ink-on-dark-dim); text-align: center; margin-bottom: 25px; font-weight: 500; }
  .glowing-text { color: var(--teal); text-shadow: 0 0 10px var(--teal-soft); }
  .roadmap-container { display: flex; flex-direction: column; gap: 12px; margin-bottom: 25px; }
  .roadmap-step { padding: 14px; border-radius: var(--r-md); background: rgba(255,255,255,0.03); border: 1px solid var(--line-dark); cursor: pointer; }
  .roadmap-step.active { background: rgba(63,224,208,0.06); border-color: var(--teal-soft); }
  .roadmap-num { font-family: var(--font-mono); font-size: 10px; color: var(--teal); text-transform: uppercase; margin-bottom: 4px; font-weight: 700; }
  .roadmap-title { font-size: 14px; font-weight: 600; color: var(--ink-on-dark); margin-bottom: 2px; }
  .roadmap-desc { font-size: 12px; color: var(--ink-on-dark-dim); }
  .carousel-wrapper { overflow-x: auto; display: flex; gap: 10px; padding-bottom: 10px; margin-bottom: 25px; scrollbar-width: none; }
  .carousel-wrapper::-webkit-scrollbar { display: none; }
  .carousel-card { flex: 0 0 85%; background: rgba(0,0,0,0.4); border: 1px solid var(--line-dark); padding: 14px; border-radius: var(--r-md); }
  .carousel-tag { font-family: var(--font-mono); font-size: 8px; color: var(--amber); text-transform: uppercase; margin-bottom: 6px; }
  .carousel-prompt { font-family: var(--font-mono); font-size: 11px; color: var(--metal-1); line-height: 1.4; background: rgba(0,0,0,0.3); padding: 8px; border-radius: var(--r-sm); }
  .resource-card { background: rgba(4,8,14,0.6); border: 1px solid var(--line-dark); padding: 16px; border-radius: var(--r-lg); margin-bottom: 20px; }
  .resource-card h3 { font-size: 14px; color: var(--ink-on-dark); margin-bottom: 8px; font-weight: 700; }
  .resource-text { font-size: 12px; color: var(--ink-on-dark-dim); line-height: 1.4; }
  .floating-action-container { position: sticky; bottom: 16px; left: 0; right: 0; z-index: 100; width: 100%; padding: 0 4px; }
  .btn-silver { color: var(--ink-on-metal); font-weight: 800; border: 1px solid var(--line-metal); background: linear-gradient(135deg, #fff, #b4c0cc); box-shadow: 0 8px 24px rgba(255,255,255,0.15), var(--inset-metal); text-transform: uppercase; letter-spacing: 0.05em; font-size: 14px; }
  .tabs{display:flex; border-bottom:1px solid var(--line-dark); margin:12px 0; overflow-x:auto; scrollbar-width:none;}
  .tab{padding:10px 14px; cursor:pointer; color:var(--ink-on-dark-dim); border-bottom:2px solid transparent; font-family:var(--font-mono); font-size:11px; text-transform:uppercase; flex-shrink:0;}
  .tab.active{color:var(--teal); border-bottom-color:var(--teal);}
  .tab-content{display:none;}
  .tab-content.active{display:block;}
  .card{padding:16px; margin-bottom:12px;}
  .card h2{font-weight:700; font-size:15px; color:var(--ink-on-dark); margin-bottom:10px;}
  .form-group{margin-bottom:10px;}
  .form-group label{display:block; font-family:var(--font-mono); font-size:9px; color:var(--ink-on-dark-dim); text-transform:uppercase; margin-bottom:3px;}
  .glz-field{width:100%; padding:10px 12px; font-family:var(--font-mono); font-size:12px; color:var(--ink-on-dark); background:rgba(4,8,14,.55); border:1px solid var(--line-dark); border-radius:var(--r-md); outline:none;}
  .glz-field:focus{border-color:var(--teal);}
  select.glz-field{appearance:none; -webkit-appearance:none; background-image:linear-gradient(45deg,transparent 50%,var(--ink-on-dark-dim) 50%),linear-gradient(135deg,var(--ink-on-dark-dim) 50%,transparent 50%); background-position:calc(100% - 14px) 50%,calc(100% - 9px) 50%; background-size:5px 5px,5px 5px; background-repeat:no-repeat;}
  .btn{display:inline-flex; align-items:center; justify-content:center; padding:12px 16px; font-family:var(--font-ui); font-size:13px; font-weight:600; border-radius:var(--r-md); cursor:pointer; border:none; width:100%; transition: opacity var(--t-base);}
  .btn-primary{color:var(--ink-on-metal); font-weight:700; background:linear-gradient(135deg,var(--teal-bright),var(--teal)); box-shadow:0 0 14px rgba(63,224,208,.25);}
  .btn-metal{color:var(--ink-on-metal); font-weight:700; border:1px solid var(--line-metal); background:linear-gradient(145deg,var(--metal-hi),var(--metal-2));}
  .chat-box{height:240px; overflow-y:auto; border:1px solid var(--line-dark); padding:10px; border-radius:8px; background:rgba(0,0,0,.3); margin-bottom:10px; font-family:var(--font-mono); font-size:12px;}
  .chat-msg{margin-bottom:8px; padding:6px 10px; border-radius:6px; max-width:85%;}
  .chat-msg.user{background:var(--glazier-glass-1); margin-left:auto; color:#fff;}
  .chat-msg.assistant{background:rgba(255,255,255,.05); color:var(--ink-on-dark-dim); white-space:pre-wrap;}
  .result-area{background:rgba(4,8,14,.6); border:1px solid var(--line-dark); border-radius:var(--r-md); padding:12px; font-family:var(--font-mono); font-size:12px; white-space:pre-wrap; margin-top:10px; color:var(--ink-on-dark-dim);}
  .img-output{width:100%; border-radius:6px; border:1px solid var(--line-dark); margin-top:10px;}
  .toast{position:fixed; bottom:20px; left:50%; transform:translateX(-50%); z-index:3000; padding:10px 16px; border-radius:var(--r-md); font-family:var(--font-mono); font-size:11px; color:var(--teal); background:var(--glazier-glass-2); border:1px solid var(--teal-soft);}
  .footer{padding:20px 0; text-align:center; font-family:var(--font-mono); font-size:9px; color:var(--ink-on-dark-dim); border-top: 1px solid rgba(255,255,255,0.03); margin-top: 15px;}

  /* ── REAL-TIME PIPELINE PROGRESS BAR COMPONENT STYLES ── */
  .progress-box { margin-top: 15px; padding: 14px; background: rgba(0,0,0,0.45); border: 1px solid var(--line-dark); border-radius: var(--r-md); }
  .progress-header { display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: 11px; color: var(--teal); margin-bottom: 8px; font-weight: bold;}
  .progress-bar-bg { width: 100%; height: 6px; background: rgba(255,255,255,0.05); border-radius: 3px; overflow: hidden; margin-bottom: 12px; }
  .progress-bar-fill { width: 0%; height: 100%; background: linear-gradient(90deg, var(--teal), var(--teal-bright)); transition: width 0.4s ease; }
  .step-list { display: flex; flex-direction: column; gap: 6px; }
  .step-item { display: flex; align-items: center; justify-content: space-between; font-family: var(--font-mono); font-size: 10px; color: var(--ink-on-dark-dim); }
  .step-item.active { color: var(--teal); font-weight: 700; }
  .step-item.completed { color: var(--teal-bright); opacity: 0.6; }
  .step-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--ink-on-dark-dim); }
  .step-item.active .step-dot { background: var(--teal); box-shadow: 0 0 8px var(--teal); }
  .step-item.completed .step-dot { background: var(--teal-bright); }
  </style>
</head>
<body>

  <div class="app-viewport">
    <div class="bg"></div>

    <div class="marquee" id="top-banner">
      <div class="marquee-track">
        <span>◆ <span class="yt-u">YOU</span>TUBE content creation ◆ <span class="yt-u">YOU</span>TUBE content creation ◆ <span class="yt-u">YOU</span>TUBE content creation ◆ <span class="yt-u">YOU</span>TUBE content creation</span>
      </div>
    </div>

    <!-- ── INTERFACE COMPONENT A: ONBOARDING & LANDING PAGE ── -->
    <div class="wrap" id="landing-portal">
      <header class="brand-hero">
        <h1 class="logo">Logiclemon<em>AI</em></h1>
        <p class="sub">Glazier Studio Onboarding Engine</p>
      </header>
      
      <h2 class="landing-heading">Design. Automate.<br>Distribute.</h2>
      <p class="landing-subhead">Premium AI Forge optimized for automated <span class="glowing-text">short-form scale</span></p>
      
      <div class="roadmap-container">
        <div class="roadmap-step active" id="step-auth-node">
          <div class="roadmap-num">Step 01 / Security Node</div>
          <div class="roadmap-title">Authenticate Workspace</div>
          <div class="roadmap-desc" style="margin-bottom: 12px;">Establish a secure edge-session to lock your AI content and analytics configurations.</div>
          
          <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 10px;">
            <button class="btn btn-metal" onclick="initiateGoogleLogin()" style="padding: 10px; font-size: 11px; font-family: var(--font-mono); gap: 6px; justify-content: center;">
              🌐 Continue with Google Secure ID
            </button>
          </div>

          <p style="font-family: var(--font-mono); font-size: 8px; color: var(--teal); margin-top: 10px; opacity: 0.8; text-align: center;">
            🔒 Secured via end-to-end edge validation token protocols. Credentials are never written to plaintext logs.
          </p>
        </div>

        <div class="roadmap-step" onclick="tapStep(this)">
          <div class="roadmap-num">Step 02 / Core Engine</div>
          <div class="roadmap-title">Pick Your Niche & Engine</div>
          <div class="roadmap-desc">Toggle text structures via Gemini, or deploy visual assets with FLUX & Google Imagen 3.</div>
        </div>
        <div class="roadmap-step" onclick="tapStep(this)">
          <div class="roadmap-num">Step 03 / Lifecycle</div>
          <div class="roadmap-title">Launch Automated Distribution</div>
          <div class="roadmap-desc">Queue optimized programmatic scripts and synchronize native webhook triggers.</div>
        </div>
      </div>

      <div class="resource-card">
        <h3>⚡ Visual Inspiration Lab</h3>
        <div class="carousel-wrapper">
          <div class="carousel-card">
            <div class="carousel-tag">Cinematic Realism</div>
            <div class="carousel-prompt">"Cinematic cyberpunk streetscape, neon teal accents, hyper-detailed 8k texture, shot on 35mm lens, atmospheric volumetric lighting"</div>
          </div>
        </div>
      </div>

      <div class="floating-action-container">
        <button class="btn btn-silver" onclick="unlockCreationStudio()">Bypass & Explore Workspace</button>
      </div>
    </div>

    <!-- ── INTERFACE COMPONENT B: MAIN CREATION WORKSPACE ── -->
    <div class="wrap" id="studio-workspace" style="display: none; opacity: 0; transition: opacity var(--t-base) var(--ease);">
      <header class="brand-hero">
        <h1 class="logo">Logiclemon<em>AI</em></h1>
        <p class="sub">AI Assistant & Premium Image Forge</p>
      </header>

      <main>
        <div class="tabs">
          <div class="tab active" onclick="switchTab('chat')">AI Assistant</div>
          <div class="tab" onclick="switchTab('images')">Image Lab</div>
          <div class="tab" onclick="switchTab('social')">Social Desk</div>
          <div class="tab" onclick="switchTab('history')">History Logs</div>
        </div>

        <div id="tab-chat" class="tab-content active">
          <div class="card glz-surface-glass">
            <h2>Creator Assistant Chat</h2>
            <div class="chat-box" id="chat-stream">
              <div class="chat-msg assistant">Hello! I am your production copilot. Let's engineer prompts, brainstorm post architectures, or format short-form scripts.</div>
            </div>
            <div style="display:flex; gap:6px;">
              <input type="text" id="chat-input" class="glz-field" placeholder="Type instructions or prompt concepts..." style="flex:1;" />
              <button class="btn btn-primary" onclick="submitChat()" style="width:70px;">Send</button>
            </div>
          </div>
        </div>

        <div id="tab-images" class="tab-content">
          <div class="card glz-surface-glass">
            <h2>Direct Neural Image Generator</h2>
            <div class="form-group">
              <label>Visual Engine Provider</label>
              <select id="image-model" class="glz-field">
                <option value="bfl/flux-2-pro-preview">Black Forest Labs — FLUX.2 Pro (Ultra Text & Detail)</option>
                <option value="bfl/flux-pro-1.1">Black Forest Labs — FLUX 1.1 Pro (High-Speed Realism)</option>
                <option value="google/imagen-3">Google Cloud — Imagen 3 Premium (Photorealistic Clarity)</option>
                <option value="openai/gpt-image-2">OpenAI — GPT Image 2 (Advanced Prompt Compliance)</option>
                <option value="openai/dall-e-3">OpenAI — DALL-E 3 (Vector Layouts & Graphics)</option>
              </select>
            </div>
            <div class="form-group">
              <label>Prompt Description</label>
              <input type="text" id="image-prompt" class="glz-field" placeholder="Describe the scene layout parameters explicitly..." />
            </div>
            <button id="img-btn" class="btn btn-primary" onclick="triggerImageForge()">Execute Immediate Generation</button>
            <div id="img-loading-status" style="display:none; font-family:var(--font-mono); font-size:11px; color:var(--amber); margin-top:10px;">
              Executing secure edge-handshake...
            </div>
            <div id="image-result-tray"></div>
          </div>
        </div>

        <div id="tab-social" class="tab-content">
          <div class="card glz-surface-glass">
            <h2>Short-Form Content Factory</h2>
            <div class="form-group">
              <label>Target Framework Node</label>
              <select id="social-platform" class="glz-field" onchange="togglePipelineFields()">
                <option value="shorts">YouTube Shorts Script (60-Sec High Retention)</option>
                <option value="x">Micro-Post Thread Package (X Platform Layout)</option>
                <option value="deep_pipeline">YouTube Deep Production Line (7-Step Automated Pipeline)</option>
              </select>
            </div>

            <!-- Dynamic Pipeline Variables (Hidden by default unless Pipeline selected) -->
            <div id="pipeline-config-group" style="display: none; transition: opacity var(--t-base);">
              <div class="form-group">
                <label>Target Audience Demographic</label>
                <input type="text" id="pipeline-audience" class="glz-field" placeholder="e.g., Tech Founders, Gen Z Designers" value="General Audience" />
              </div>
              <div style="display: flex; gap: 8px;">
                <div class="form-group" style="flex: 1;">
                  <label>Language Output</label>
                  <select id="pipeline-lang" class="glz-field">
                    <option value="en">English</option>
                    <option value="hi">Hindi</option>
                    <option value="ru">Russian</option>
                    <option value="id">Indonesian</option>
                    <option value="tr">Turkish</option>
                    <option value="pt">Portuguese</option>
                  </select>
                </div>
                <div class="form-group" style="flex: 1;">
                  <label>Compute Tier Level</label>
                  <select id="pipeline-tier" class="glz-field">
                    <option value="standard">Standard (Gemini Core)</option>
                    <option value="pro">Pro (Gemma-4 Pro Array)</option>
                    <option value="premium" selected>Premium (Gemini-3.1-Pro)</option>
                  </select>
                </div>
              </div>
            </div>

            <div class="form-group">
              <label>Core Topic Focus</label>
              <input type="text" id="social-topic" class="glz-field" placeholder="e.g., Why Edge Computing wins in 2026" />
            </div>

            <button id="social-btn" class="btn btn-primary" onclick="triggerSocialCompose()">Compose Social Assets</button>

            <!-- Real-Time Pipeline Progress Tracker (Polled Dynamically) -->
            <div id="pipeline-tracker" class="progress-box" style="display: none;">
              <div class="progress-header">
                <span id="tracker-step-title">Stage 0: Handshake</span>
                <span id="tracker-step-percent">0%</span>
              </div>
              <div class="progress-bar-bg">
                <div id="tracker-bar-fill" class="progress-bar-fill"></div>
              </div>
              <div class="step-list">
                <div class="step-item" id="pstep-1"><span>1. Search Engine Researching</span> <div class="step-dot"></div></div>
                <div class="step-item" id="pstep-2"><span>2. Video Script Hook & CTA Elements</span> <div class="step-dot"></div></div>
                <div class="step-item" id="pstep-3"><span>3. Conversational Content Sections</span> <div class="step-dot"></div></div>
                <div class="step-item" id="pstep-4"><span>4. SEO Meta tags & Description</span> <div class="step-dot"></div></div>
                <div class="step-item" id="pstep-5"><span>5. Thumbnail Concept Layout Design</span> <div class="step-dot"></div></div>
                <div class="step-item" id="pstep-6"><span>6. Rendering High-Definition Artwork</span> <div class="step-dot"></div></div>
                <div class="step-item" id="pstep-7"><span>7. Database Storage Allocation</span> <div class="step-dot"></div></div>
              </div>
            </div>

            <div class="result-area" id="social-result-box" style="display:none;"></div>
          </div>
        </div>

        <div id="tab-history" class="tab-content">
          <div class="card glz-surface-glass">
            <h2>Historical Run Indexes</h2>
            <button class="btn btn-metal" onclick="fetchHistoryIndex()" style="margin-bottom:10px;">Query Database Ports</button>
            <div id="history-container-box" style="font-family:var(--font-mono); font-size:12px; color:var(--ink-on-dark-dim); display: flex; flex-direction: column; gap: 8px;">No active telemetry arrays retrieved.</div>
          </div>
        </div>
      </main>

      <footer class="footer">
        <p class="brand-mark">LogiclemonAI • Restored Build 2026</p>
      </footer>
    </div>
  </div>

  <script>
    var WA = window.Telegram.WebApp;
    WA.ready();
    WA.expand();
    WA.enableClosingConfirmation();

    function syncTelegramTheme() {
      var params = WA.themeParams;
      if (params && Object.keys(params).length > 0) {
        var root = document.documentElement;
        if (params.bg_color) root.style.setProperty('--bg-void', params.bg_color);
        if (params.secondary_bg_color) root.style.setProperty('--bg-base', params.secondary_bg_color);
        if (params.text_color) root.style.setProperty('--ink-on-dark', params.text_color);
        if (params.hint_color) root.style.setProperty('--ink-on-dark-dim', params.hint_color);
        if (params.button_color) {
          root.style.setProperty('--teal', params.button_color);
          root.style.setProperty('--teal-bright', params.button_color);
        }
        if (params.button_text_color) root.style.setProperty('--ink-on-metal', params.button_text_color);
      }
    }
    syncTelegramTheme();
    WA.onEvent('themeChanged', syncTelegramTheme);

    var uid = (WA.initDataUnsafe && WA.initDataUnsafe.user && WA.initDataUnsafe.user.id) ? WA.initDataUnsafe.user.id : 'anon';
    var chatHistoryArr = [];

    const urlParams = new URLSearchParams(window.location.search);
    if(urlParams.get('auth') === 'success') {
      document.getElementById('landing-portal').style.display = 'none';
      const ws = document.getElementById('studio-workspace');
      ws.style.display = 'block';
      ws.style.opacity = '1';
      if(urlParams.get('tg_user')) { uid = urlParams.get('tg_user'); }
      toast('Identity authenticated successfully');
    }

    function togglePipelineFields() {
      var val = document.getElementById('social-platform').value;
      var configGroup = document.getElementById('pipeline-config-group');
      if (val === 'deep_pipeline') {
        configGroup.style.display = 'block';
      } else {
        configGroup.style.display = 'none';
      }
    }

    function initiateGoogleLogin() {
      window.location.href = '/api/auth/google?tg_user=' + uid;
    }

    function tapStep(element) {
      document.querySelectorAll('.roadmap-step').forEach(function(s) { s.classList.remove('active'); });
      element.classList.add('active');
      WA.HapticFeedback.impactOccurred('light');
    }

    function unlockCreationStudio() {
      WA.HapticFeedback.notificationOccurred('success');
      var portal = document.getElementById('landing-portal');
      var studio = document.getElementById('studio-workspace');
      portal.style.display = 'none';
      studio.style.display = 'block';
      setTimeout(function() { studio.style.opacity = '1'; }, 50);
    }

    function switchTab(name) {
      document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
      document.querySelectorAll('.tab-content').forEach(function(t) { t.classList.remove('active'); });
      var tabEl = Array.from(document.querySelectorAll('.tab')).find(function(t) { return t.getAttribute('onclick').indexOf(name) !== -1; });
      if(tabEl) tabEl.classList.add('active');
      var contentEl = document.getElementById('tab-' + name);
      if(contentEl) contentEl.classList.add('active');
      WA.HapticFeedback.impactOccurred('light');
    }

    function toast(text) {
      var el = document.createElement('div'); el.className = 'toast'; el.textContent = text;
      document.body.appendChild(el); setTimeout(function() { el.remove(); }, 3000);
    }

    async function submitChat() {
      var inp = document.getElementById('chat-input'); var txt = inp.value.trim(); if(!txt) return;
      inp.value = ''; var box = document.getElementById('chat-stream');
      box.innerHTML += '<div class="chat-msg user">' + txt + '</div>'; box.scrollTop = box.scrollHeight;
      try {
        var resp = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: txt, history: chatHistoryArr }) });
        var data = await resp.json();
        
        if(data.error) {
          box.innerHTML += '<div class="chat-msg assistant" style="color:var(--ember);"><strong>' + data.error + '</strong><br>' + (data.detail || '') + '</div>';
        } else {
          chatHistoryArr.push({ role: 'user', content: txt }); chatHistoryArr.push({ role: 'assistant', content: data.reply });
          box.innerHTML += '<div class="chat-msg assistant">' + data.reply + '</div>';
        }
        box.scrollTop = box.scrollHeight;
      } catch(e) { box.innerHTML += '<div class="chat-msg assistant" style="color:var(--ember);">Transit Error: ' + e.message + '</div>'; }
    }

    async function triggerImageForge() {
      var pVal = document.getElementById('image-prompt').value.trim(); if(!pVal) { WA.showAlert('Please issue a design prompt string.'); return; }
      var btn = document.getElementById('img-btn'); var loader = document.getElementById('img-loading-status'); var tray = document.getElementById('image-result-tray');
      btn.disabled = true; loader.style.display = 'block'; tray.innerHTML = '';
      try {
        var resp = await fetch('/api/generate-image', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt: pVal, model: document.getElementById('image-model').value, tg_user: uid }) });
        var data = await resp.json(); loader.style.display = 'none'; btn.disabled = false;
        if(data.image_url) {
          tray.innerHTML = '<div class="result-area"><strong>Engine Status:</strong> Render Complete via ' + data.provider + '</div><img src="' + data.image_url + '" class="img-output" />';
          WA.HapticFeedback.notificationOccurred('success');
        } else { 
          tray.innerHTML = '<div class="result-area" style="color:var(--ember);"><strong>Forge Failed</strong><br>' + (data.detail || 'Boundary blocked') + '</div>'; 
          WA.HapticFeedback.notificationOccurred('error'); 
        }
      } catch(err) { loader.style.display = 'none'; btn.disabled = false; tray.innerHTML = '<div class="result-area" style="color:var(--ember);">Connection Failed: ' + err.message + '</div>'; }
    }

    // ── AUTOMATED PIPELINE LONG-POLLING ORCHESTRATOR ──
    async function triggerSocialCompose() {
      var tVal = document.getElementById('social-topic').value.trim(); if(!tVal) { WA.showAlert('Please frame a target creation topic focus point.'); return; }
      var platform = document.getElementById('social-platform').value;
      var btn = document.getElementById('social-btn'); 
      var box = document.getElementById('social-result-box');
      var tracker = document.getElementById('pipeline-tracker');

      btn.disabled = true;
      box.style.display = 'none';
      box.textContent = '';

      if (platform !== 'deep_pipeline') {
        tracker.style.display = 'none';
        box.style.display = 'block';
        box.textContent = 'Running model execution frameworks...';
        try {
          var resp = await fetch('/api/social/create', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ topic: tVal, platform: platform }) });
          var data = await resp.json();
          if(data.error) {
            box.innerHTML = '<span style="color:var(--ember);"><strong>' + data.error + '</strong><br>' + (data.detail || '') + '</span>';
          } else {
            box.textContent = data.result;
            WA.HapticFeedback.notificationOccurred('success');
          }
          btn.disabled = false;
        } catch(e) { box.textContent = 'Composition exception: ' + e.message; btn.disabled = false; }
      } else {
        // Run full, multi-step asynchronous pipeline with UI feedback
        tracker.style.display = 'block';
        resetProgressUI();
        
        try {
          const startResp = await fetch('/api/pipeline/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              topic: tVal,
              lang: document.getElementById('pipeline-lang').value,
              tier: document.getElementById('pipeline-tier').value,
              audience: document.getElementById('pipeline-audience').value,
              tg_user: uid
            })
          });
          const startData = await startResp.json();
          if (!startData.success) throw new Error(startData.error || 'Failed to start pipeline cluster.');

          // Polling thread execution
          pollPipelineStatus(startData.taskId);
        } catch (err) {
          tracker.style.display = 'none';
          box.style.display = 'block';
          box.innerHTML = '<span style="color:var(--ember);"><strong>Pipeline Kickoff Failed</strong><br>' + err.message + '</span>';
          btn.disabled = false;
        }
      }
    }

    function resetProgressUI() {
      document.getElementById('tracker-step-title').textContent = 'Handshake Initialized...';
      document.getElementById('tracker-step-percent').textContent = '0%';
      document.getElementById('tracker-bar-fill').style.width = '0%';
      for (let i = 1; i <= 7; i++) {
        const item = document.getElementById('pstep-' + i);
        item.className = 'step-item';
      }
    }

    function pollPipelineStatus(taskId) {
      const interval = setInterval(async () => {
        try {
          const resp = await fetch('/api/pipeline/status?taskId=' + taskId);
          if (!resp.ok) return;
          const task = await resp.json();

          const step = task.step || 0;
          const status = task.status;

          // Update Progress Indicator Elements
          const percentage = Math.round((step / 7) * 100);
          document.getElementById('tracker-step-percent').textContent = percentage + '%';
          document.getElementById('tracker-bar-fill').style.width = percentage + '%';

          // Focus step highlighter
          for (let i = 1; i <= 7; i++) {
            const el = document.getElementById('pstep-' + i);
            if (i < step) {
              el.className = 'step-item completed';
            } else if (i === step && status === 'processing') {
              el.className = 'step-item active';
              document.getElementById('tracker-step-title').textContent = el.querySelector('span').textContent;
            } else {
              el.className = 'step-item';
            }
          }

          if (status === 'completed') {
            clearInterval(interval);
            document.getElementById('tracker-step-title').textContent = 'Pipeline Finished';
            document.getElementById('social-btn').disabled = false;
            WA.HapticFeedback.notificationOccurred('success');
            
            // Format and expose pipeline results natively inside the client
            const res = task.result ? JSON.parse(task.result) : {};
            renderPipelineOutput(res);
          } else if (status === 'error') {
            clearInterval(interval);
            document.getElementById('tracker-step-title').textContent = 'Pipeline Interrupted';
            document.getElementById('social-btn').disabled = false;
            document.getElementById('social-result-box').style.display = 'block';
            document.getElementById('social-result-box').innerHTML = '<span style="color:var(--ember);"><strong>Pipeline Error:</strong><br>' + (task.error || 'Timeout exception') + '</span>';
            WA.HapticFeedback.notificationOccurred('error');
          }
        } catch (e) {
          console.error("Pipeline monitoring lost link:", e.message);
        }
      }, 2000);
    }

    function renderPipelineOutput(res) {
      const box = document.getElementById('social-result-box');
      box.style.display = 'block';
      box.innerHTML = '';

      let html = '<div style="margin-bottom: 15px; border-bottom: 1px solid var(--line-dark); padding-bottom: 10px;">' +
                 '<h3 style="color:#fff; font-size:14px; margin-bottom: 4px;">🎬 Generated Title:</h3>' +
                 '<p style="color:var(--teal); font-weight:bold;">' + res.title + '</p>' +
                 '</div>';

      if (res.title_variants && res.title_variants.length > 0) {
        html += '<div style="margin-bottom: 15px;">' +
                '<h4 style="color:var(--ink-on-dark-dim); font-size:11px; text-transform:uppercase;">SEO Title Variants:</h4>' +
                '<ul style="list-style: none; padding-left: 0; margin-top: 5px;">' +
                res.title_variants.map(v => '<li style="padding: 4px; border-bottom: 1px solid rgba(255,255,255,0.02); font-size:11px;">- ' + v + '</li>').join('') +
                '</ul></div>';
      }

      html += '<div style="margin-bottom: 15px; background:rgba(0,0,0,0.2); padding:10px; border-radius:6px; border:1px solid var(--line-dark);">' +
              '<h4 style="color:var(--teal); font-size:11px; text-transform:uppercase; margin-bottom:4px;">💥 Opening Hook Statement:</h4>' +
              '<p style="font-size:12px; line-height:1.4;">' + res.hook + '</p>' +
              '</div>';

      if (res.sections && res.sections.length > 0) {
        html += '<h3 style="color:#fff; font-size:14px; margin: 15px 0 8px;">📖 Video Outline Sections:</h3>';
        res.sections.forEach((s, idx) => {
          html += '<div style="margin-bottom: 12px; border-left: 2px solid var(--teal); padding-left:10px;">' +
                  '<div style="display:flex; justify-content:space-between; font-size:11px; color:var(--teal); font-weight:bold;">' +
                  '<span>Section ' + (idx + 1) + ': ' + s.title + '</span>' +
                  '<span>⏱️ ' + s.timestamp + '</span>' +
                  '</div>' +
                  '<p style="font-size:12px; line-height:1.4; margin:4px 0;">' + s.content + '</p>' +
                  '<p style="font-size:10px; color:var(--ink-on-dark-dim); font-style:italic;">🎬 Visual Cue: ' + s.visual_cue + '</p>' +
                  '</div>';
        });
      }

      html += '<div style="margin-bottom: 15px; background:rgba(0,0,0,0.2); padding:10px; border-radius:6px; border:1px solid var(--line-dark);">' +
              '<h4 style="color:var(--teal); font-size:11px; text-transform:uppercase; margin-bottom:4px;">🎯 Video Outro / CTA:</h4>' +
              '<p style="font-size:12px; line-height:1.4;">' + res.cta + '</p>' +
              '</div>';

      html += '<div style="margin-bottom: 15px;">' +
              '<h4 style="color:var(--ink-on-dark-dim); font-size:11px; text-transform:uppercase;">📝 Video Description:</h4>' +
              '<p style="font-size:11px; line-height:1.4; background: rgba(0,0,0,0.4); padding:10px; border-radius:6px; white-space:pre-wrap;">' + res.description + '</p>' +
              '</div>';

      if (res.tags && res.tags.length > 0) {
        html += '<div style="margin-bottom: 15px;">' +
                '<h4 style="color:var(--ink-on-dark-dim); font-size:11px; text-transform:uppercase;">🏷️ Video Tags:</h4>' +
                '<p style="font-size:11px; line-height:1.4;">' + res.tags.join(', ') + '</p>' +
                '</div>';
      }

      if (res.thumbnail_url) {
        html += '<div style="margin-top: 15px; border-top: 1px solid var(--line-dark); padding-top: 15px;">' +
                '<h3 style="color:#fff; font-size:14px; margin-bottom: 8px;">🎨 Generated Thumbnail Artwork:</h3>' +
                '<img src="' + res.thumbnail_url + '" class="img-output" />' +
                '<p style="font-size:10px; color:var(--ink-on-dark-dim); margin-top:4px;">Concept overlay text: ' + res.thumb_text + '</p>' +
                '</div>';
      }

      box.innerHTML = html;
    }

    async function fetchHistoryIndex() {
      var box = document.getElementById('history-container-box'); box.textContent = 'Syncing system databases...';
      try {
        var r = await fetch('/api/history?tg_user=' + uid); var d = await r.json(); var items = d.items || [];
        if(!items.length) { box.textContent = 'No visual run tokens associated with user ["' + uid + '"] found.'; return; }
        
        box.innerHTML = items.map(function(i) { 
          let badge = '<span style="font-size:9px; background:rgba(63,224,208,0.2); color:var(--teal); padding:2px 6px; border-radius:3px;">Short-Form</span>';
          if (i.result && i.result.sections) {
            badge = '<span style="font-size:9px; background:rgba(246,169,59,0.2); color:var(--amber); padding:2px 6px; border-radius:3px;">Video Pipeline</span>';
          }
          return '<div style="padding:12px; border:1px solid var(--line-dark); border-radius:6px; margin-bottom:6px; background:rgba(0,0,0,.2); display:flex; flex-direction:column; gap:6px;">' +
            '<div style="display:flex; justify-content:space-between; align-items:center;">' +
              '<strong>' + i.topic + '</strong>' +
              badge +
            '</div>' +
            '<div style="font-size:11px; color:var(--ink-on-dark-dim); font-family:var(--font-mono);">' + i.title + '</div>' +
            '<span style="font-size:9px; color:var(--ink-on-dark-dim);">' + new Date(i.created_at).toLocaleDateString() + '</span>' +
            '</div>'; 
        }).join('');
      } catch(e) { box.textContent = 'Failed to execute query mapping index chains.'; }
    }
  </script>
</body>
</html>`;
}
