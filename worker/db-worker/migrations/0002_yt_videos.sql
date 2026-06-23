-- YouTube pipeline results — persisted so generated scripts/metadata/thumbnails survive restarts.
-- Additive migration: does NOT drop or alter existing tables.

CREATE TABLE IF NOT EXISTS yt_videos (
  id TEXT PRIMARY KEY,                 -- the pipeline task_id (e.g. yt_a1b2c3d4e5f6)
  topic TEXT,
  title TEXT,
  status TEXT DEFAULT 'completed',
  niche TEXT,
  target_audience TEXT,
  result TEXT DEFAULT '{}',            -- full JSON result payload (script, metadata, thumbnail_design, ...)
  execution_time REAL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_yt_videos_created ON yt_videos(created_at DESC);
