-- Lists move from storage/lists.yaml to the database.
--
-- list: a list. `name_key` is the name without accents, capitals or extra spaces: what names are compared by.
--   `language` is the language of `name` and `description` (the session where it was written), the rest of
--   the languages are in `list_translation`. `deleted_at` is a soft delete (the items are not touched).
-- list_item: an entry of a list. `text_key` is like `name_key`. `done`/`done_at` mark it as done without removing it.
--   `deleted_at` is a soft delete (the "trash"): it can be restored until the night cleanup purges it.
-- list_translation / list_item_translation: the other languages, filled by the night translation. Editing the
--   source text deletes its translations, and the night job makes them again.
--
-- A name (or an item text) can't be twice among what is not deleted. Deleted rows don't count, so the same
--   name can be used again after a delete.
BEGIN;

CREATE TABLE list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    language TEXT,
    description TEXT,
    favourite INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);

CREATE UNIQUE INDEX idx_list_name_key ON list (name_key) WHERE deleted_at IS NULL;

CREATE TABLE list_translation (
    list_id INTEGER NOT NULL REFERENCES list (id) ON DELETE CASCADE,
    language TEXT NOT NULL,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    description TEXT,
    PRIMARY KEY (list_id, language)
);

CREATE TABLE list_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id INTEGER NOT NULL REFERENCES list (id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    text_key TEXT NOT NULL,
    language TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    done_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);

CREATE INDEX idx_list_item_list ON list_item (list_id);
CREATE UNIQUE INDEX idx_list_item_text_key ON list_item (list_id, text_key) WHERE deleted_at IS NULL;

CREATE TABLE list_item_translation (
    item_id INTEGER NOT NULL REFERENCES list_item (id) ON DELETE CASCADE,
    language TEXT NOT NULL,
    text TEXT NOT NULL,
    text_key TEXT NOT NULL,
    PRIMARY KEY (item_id, language)
);

PRAGMA user_version = 5;

COMMIT;
