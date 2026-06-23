export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return cors(new Response(null, { status: 204 }));
    }

    const auth = request.headers.get('Authorization');
    if (!env.API_TOKEN) {
      return cors(new Response(JSON.stringify({ error: 'Server misconfigured: API_TOKEN is not set' }), { status: 500, headers: { 'Content-Type': 'application/json' } }));
    }
    if (auth !== `Bearer ${env.API_TOKEN}`) {
      return cors(new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401, headers: { 'Content-Type': 'application/json' } }));
    }

    const url = new URL(request.url);
    const path = url.pathname.replace(/^\/db/, '') || '/';

    try {
      let result;
      let m;

      // Health check
      if (request.method === 'GET' && path === '/health') {
        result = { status: 'healthy', database: !!env.DB };
      }

      // content_requests
      else if (request.method === 'POST' && path === '/content_requests') {
        result = await createRecord(env.DB, 'content_requests', await request.json());
      }
      else if (request.method === 'GET' && (m = path.match(/^\/content_requests\/(.+)$/))) {
        result = await getRecord(env.DB, 'content_requests', m[1]);
      }
      else if (request.method === 'PATCH' && (m = path.match(/^\/content_requests\/(.+)$/))) {
        result = await updateRecord(env.DB, 'content_requests', m[1], await request.json());
      }
      else if (request.method === 'GET' && path === '/content_requests') {
        result = await listRecords(env.DB, 'content_requests', url.searchParams);
      }

      // content_pieces
      else if (request.method === 'POST' && path === '/content_pieces') {
        result = await createRecord(env.DB, 'content_pieces', await request.json());
      }
      else if (request.method === 'GET' && (m = path.match(/^\/content_pieces\/(.+)$/))) {
        result = await getRecord(env.DB, 'content_pieces', m[1]);
      }
      else if (request.method === 'PATCH' && (m = path.match(/^\/content_pieces\/(.+)$/))) {
        result = await updateRecord(env.DB, 'content_pieces', m[1], await request.json());
      }
      else if (request.method === 'GET' && path === '/content_pieces') {
        result = await listRecords(env.DB, 'content_pieces', url.searchParams);
      }

      // agent_tasks
      else if (request.method === 'POST' && path === '/agent_tasks') {
        result = await createRecord(env.DB, 'agent_tasks', await request.json());
      }
      else if (request.method === 'PATCH' && (m = path.match(/^\/agent_tasks\/(.+)$/))) {
        result = await updateRecord(env.DB, 'agent_tasks', m[1], await request.json());
      }
      else if (request.method === 'GET' && path === '/agent_tasks') {
        result = await listRecords(env.DB, 'agent_tasks', url.searchParams);
      }

      // quality_assessments
      else if (request.method === 'POST' && path === '/quality_assessments') {
        result = await createRecord(env.DB, 'quality_assessments', await request.json());
      }
      else if (request.method === 'GET' && path === '/quality_assessments') {
        result = await listRecords(env.DB, 'quality_assessments', url.searchParams);
      }

      // yt_videos (YouTube pipeline results — persisted scripts/metadata/thumbnail)
      else if (request.method === 'POST' && path === '/yt_videos') {
        result = await createRecord(env.DB, 'yt_videos', await request.json());
      }
      else if (request.method === 'GET' && (m = path.match(/^\/yt_videos\/(.+)$/))) {
        result = await getRecord(env.DB, 'yt_videos', m[1]);
      }
      else if (request.method === 'GET' && path === '/yt_videos') {
        result = await listRecords(env.DB, 'yt_videos', url.searchParams);
      }

      // stats
      else if (request.method === 'GET' && path === '/stats') {
        result = await getStats(env.DB);
      }

      // content with request (join)
      else if (request.method === 'GET' && (m = path.match(/^\/content_with_request\/(.+)$/))) {
        result = await getContentWithRequest(env.DB, m[1]);
      }

      else {
        return cors(new Response(JSON.stringify({ error: 'Not found' }), { status: 404, headers: { 'Content-Type': 'application/json' } }));
      }

      return cors(new Response(JSON.stringify(result), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    } catch (err) {
      return cors(new Response(JSON.stringify({ error: err.message }), { status: 500, headers: { 'Content-Type': 'application/json' } }));
    }
  }
};

async function createRecord(db, table, data) {
  const id = data.id || crypto.randomUUID();
  const now = new Date().toISOString();
  const insertData = { ...data, id, created_at: data.created_at || now, updated_at: data.updated_at || now };

  const keys = Object.keys(insertData);
  const placeholders = keys.map((_, i) => `?`).join(', ');
  const values = keys.map(k => {
    const v = insertData[k];
    return typeof v === 'object' ? JSON.stringify(v) : v;
  });

  await db.prepare(`INSERT INTO ${table} (${keys.join(', ')}) VALUES (${placeholders})`).bind(...values).run();
  return { id };
}

async function getRecord(db, table, id) {
  const result = await db.prepare(`SELECT * FROM ${table} WHERE id = ?`).bind(id).first();
  if (!result) return null;
  return parseJsonFields(result);
}

async function updateRecord(db, table, id, data) {
  data.updated_at = new Date().toISOString();
  const keys = Object.keys(data);
  const setClause = keys.map(k => `${k} = ?`).join(', ');
  const values = keys.map(k => {
    const v = data[k];
    return typeof v === 'object' ? JSON.stringify(v) : v;
  });

  const result = await db.prepare(`UPDATE ${table} SET ${setClause} WHERE id = ?`).bind(...values, id).run();
  return { success: result.success };
}

async function listRecords(db, table, params) {
  const limit = parseInt(params.get('limit') || '10');
  const offset = parseInt(params.get('offset') || '0');
  const userId = params.get('user_id');
  const requestId = params.get('request_id');
  const contentId = params.get('content_id');

  let where = '';
  let bindValues = [];

  if (table === 'content_requests' && userId) {
    where = 'WHERE user_id = ?';
    bindValues.push(userId);
  }
  if (table === 'content_pieces' && requestId) {
    where = 'WHERE request_id = ?';
    bindValues.push(requestId);
  }
  if (table === 'quality_assessments' && contentId) {
    where = 'WHERE content_id = ?';
    bindValues.push(contentId);
  }
  if (table === 'agent_tasks' && requestId) {
    where = 'WHERE content_request_id = ?';
    bindValues.push(requestId);
  }

  const countResult = await db.prepare(`SELECT COUNT(*) as total FROM ${table} ${where}`).bind(...bindValues).first();
  const dataResult = await db.prepare(`SELECT * FROM ${table} ${where} ORDER BY created_at DESC LIMIT ? OFFSET ?`).bind(...bindValues, limit, offset).all();

  return {
    data: (dataResult.results || []).map(parseJsonFields),
    total: countResult?.total || 0,
    limit,
    offset
  };
}

async function getStats(db) {
  const requests = await db.prepare(`SELECT status FROM content_requests`).all();
  const rows = requests.results || [];
  const total = rows.length;
  const completed = rows.filter(r => r.status === 'completed').length;
  const failed = rows.filter(r => r.status === 'failed').length;
  const pending = rows.filter(r => ['pending', 'processing'].includes(r.status)).length;

  return {
    total_requests: total,
    completed,
    failed,
    pending,
    success_rate: total > 0 ? (completed / total * 100) : 0
  };
}

async function getContentWithRequest(db, contentId) {
  const content = await db.prepare(`SELECT * FROM content_pieces WHERE id = ?`).bind(contentId).first();
  if (!content) return null;

  const result = parseJsonFields(content);
  if (result.request_id) {
    const req = await db.prepare(`SELECT * FROM content_requests WHERE id = ?`).bind(result.request_id).first();
    if (req) result.request = parseJsonFields(req);
  }
  return result;
}

function parseJsonFields(row) {
  if (!row) return row;
  const parsed = { ...row };
  for (const key of ['metadata', 'input_data', 'output_data', 'details', 'result']) {
    if (typeof parsed[key] === 'string') {
      try { parsed[key] = JSON.parse(parsed[key]); } catch {}
    }
  }
  return parsed;
}

function cors(resp) {
  const headers = new Headers(resp.headers);
  headers.set('Access-Control-Allow-Origin', '*');
  headers.set('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS');
  headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  return new Response(resp.body, { status: resp.status, statusText: resp.statusText, headers });
}
