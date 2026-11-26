-- Support for the nightly memory consolidation.
--
-- memory_meta: small key/value facts shared by every process that opens the database
--   (when the last consolidation ran, the lock of the one running). The state file of the app can't do it:
--   the consolidation runs in the Support process and the application reads when it ran.
-- long_time_memory.stale: 1 when the topic was updated in another language and this version still has to be
--   regenerated from it.
BEGIN;

ALTER TABLE long_time_memory ADD COLUMN stale INTEGER NOT NULL DEFAULT 0;

CREATE TABLE memory_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

PRAGMA user_version = 3;

COMMIT;
