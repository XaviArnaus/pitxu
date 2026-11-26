-- Memory model for the short / long term split with one entry per language.
--
-- short_time_memory: where everything new lands, in the language of the session.
--   status: pending (waits for the nightly consolidation), consolidated, ignored.
-- long_time_memory: written only by the nightly consolidation (and the preload).
--   One row per topic and language. The rows of the same topic share the topic_id.
-- pending_conversations: raw chat histories that could not be summarized (the LLM failed). They are retried later.
--
-- The language of the existing rows is left empty here: the config knows which one it is (memory.legacy_entries_language),
--   so it is set at startup by the code, right after the migrations.
BEGIN;

ALTER TABLE short_time_memory ADD COLUMN language TEXT;
ALTER TABLE short_time_memory ADD COLUMN status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE short_time_memory ADD COLUMN consolidated_at TIMESTAMP;
ALTER TABLE short_time_memory ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE short_time_memory ADD COLUMN topic_id INTEGER;
ALTER TABLE short_time_memory ADD COLUMN preload_key TEXT;

ALTER TABLE long_time_memory ADD COLUMN language TEXT;
ALTER TABLE long_time_memory ADD COLUMN topic_id INTEGER;
ALTER TABLE long_time_memory ADD COLUMN updated_at TIMESTAMP;
ALTER TABLE long_time_memory ADD COLUMN source_short_ids TEXT;
ALTER TABLE long_time_memory ADD COLUMN preload_key TEXT;

-- Whatever was in the long term memory before is its own topic.
UPDATE long_time_memory SET topic_id = id WHERE topic_id IS NULL;

CREATE UNIQUE INDEX idx_long_time_memory_topic_language ON long_time_memory (topic_id, language);
CREATE INDEX idx_long_time_memory_preload_key ON long_time_memory (preload_key);
CREATE INDEX idx_short_time_memory_status ON short_time_memory (status);

CREATE TABLE pending_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    language TEXT,
    history_json TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

PRAGMA user_version = 2;

COMMIT;
