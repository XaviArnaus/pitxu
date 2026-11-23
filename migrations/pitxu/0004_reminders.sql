-- Reminders move from storage/reminders.yaml to the database.
--
-- due_at: the local date and time of the reminder as "YYYY-MM-DD HH:MM", so comparing the text orders by time.
-- announced_at: when it was announced. NULL while it is pending. Announced reminders are kept for a while
--   (and pruned at night), so a late "snooze that one" can find them and an announcement is never repeated.
-- language: the language of the session where it was created.
BEGIN;

CREATE TABLE reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    due_at TEXT NOT NULL,
    text TEXT NOT NULL,
    language TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    announced_at TIMESTAMP
);

CREATE INDEX idx_reminders_pending ON reminders (announced_at, due_at);

PRAGMA user_version = 4;

COMMIT;
