DROP TABLE IF EXISTS quality_assessments;
DROP TABLE IF EXISTS agent_tasks;
DROP TABLE IF EXISTS content_pieces;
DROP TABLE IF EXISTS content_requests;

CREATE TABLE content_requests (
  id TEXT PRIMARY KEY,
  user_id TEXT,
  topic TEXT NOT NULL,
  content_type TEXT DEFAULT 'article',
  target_audience TEXT DEFAULT 'general',
  style_requirements TEXT,
  status TEXT DEFAULT 'pending',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE content_pieces (
  id TEXT PRIMARY KEY,
  request_id TEXT REFERENCES content_requests(id),
  title TEXT,
  content TEXT,
  metadata TEXT DEFAULT '{}',
  quality_score REAL DEFAULT 0.0,
  seo_score REAL DEFAULT 0.0,
  fact_check_score REAL DEFAULT 0.0,
  status TEXT DEFAULT 'draft',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE agent_tasks (
  id TEXT PRIMARY KEY,
  content_request_id TEXT REFERENCES content_requests(id),
  agent_type TEXT,
  input_data TEXT DEFAULT '{}',
  output_data TEXT DEFAULT '{}',
  execution_time REAL DEFAULT 0,
  status TEXT DEFAULT 'pending',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE quality_assessments (
  id TEXT PRIMARY KEY,
  content_id TEXT REFERENCES content_pieces(id),
  assessment_type TEXT,
  score REAL,
  details TEXT DEFAULT '{}',
  assessed_at TEXT NOT NULL
);
