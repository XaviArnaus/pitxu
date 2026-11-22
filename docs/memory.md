# Memory

Pitxu remembers in two levels, both in the SQLite database (`storage/db/pitxu.db`, see `config/database.yaml`).

| | Short term | Long term |
| --- | --- | --- |
| Table | `short_time_memory` | `long_time_memory` |
| Who writes | The chatbot (tools) and the summaries of the conversations | Only the nightly consolidation and the preload |
| What it holds | Everything new, in the language it was said | Topics, **one entry per language** (en, es, ca, de) |
| Chatbot | Reads and edits | Reads only (the database refuses any write) |

## The flow

1. **During a conversation** the chatbot creates entries with its tools. They are `pending` in the short term memory.
2. **When a conversation ends** (the chatbot decides it, the user says goodbye, or the application closes) it is summarized by an LLM into a short term entry, in the background. "Nothing worth remembering" is a valid outcome (nothing is stored). `memory.min_user_turns` sets how much the user must say. If the summary fails, the raw conversation is kept in `pending_conversations` and summarized later.
3. **Every night** (with the night tasks, at the time of `night_tasks` in `main.yaml`; only when nobody is talking to Pitxu; a catch-up runs after the start if the Raspberry was off) the consolidation sends the pending entries, in batches, to an LLM together with the existing topics of that language. The LLM returns *create*, *update* or *ignore* operations, applied all or nothing. A topic that changes is then translated to the other languages. A backup of the database is made first (only if there is something to do). The consolidation gives way when something is waiting in the Support queue.
4. **Consolidated entries stay 14 days** in the short term memory (`memory.short_term.retention_days`) and are then deleted. Meanwhile the chatbot reads them first.

An entry that fails to consolidate is retried up to `memory.consolidation.max_attempts` times, then marked `failed`: it stays searchable and is never tried again.

## What the chatbot sees

- Every id has a prefix: `S:12` (short term) and `L:5` (long term).
- A search is by **keywords** (one to three short words, not a whole question): it looks in the title and in the content of the entries, in both memories, ignoring case, accents and common words, and any of the words counts. The best matches stay (`memory.search.max_results`, 8 by default), and the short term entries come first (they are the most recent; if two entries contradict each other, the newest wins). A long term topic is returned once, in the language of the conversation (otherwise the default language, otherwise any), and never a version that waits to be regenerated. A consolidated short term entry is not repeated when its topic is in the results.
- **Editing an `L:` entry** does not touch it: the edit is saved as a new short term entry (a correction, with the complete corrected content, linked to the topic). It is visible immediately, the long term entry is flagged `pending_correction`, and the consolidation applies it overnight.
- **Forgetting** an `S:` entry that is not in the long term memory deletes it. Forgetting an `L:` entry (or an entry that is already part of a topic) is only **registered** as a short term entry `FORGET REQUEST (not applied): ...`: the long term memory, and the preload in it, is never deleted by the chatbot. The long term entry is flagged `forget_requested_on` and the chatbot tells the user that it was asked to forget it but is not allowed to. Forget requests are never consolidated nor pruned: removing one is a manual action.

## Autonomy and what the screen shows

The memory is Pitxu's own: with `chatbot.memory_autonomy: True` the system instruction gets `chatbot.memory_autonomy_instruction`, which makes the chatbot save what is worth keeping without asking and without announcing it (never secrets), update an existing entry instead of duplicating it, search silently before answering what may depend on the past, and forget without asking again when the user asks for it. With `False` the instruction is not added.

Whatever the chatbot writes (new, updated, correction pending, forget request registered, forgotten) is notified for a few seconds in the top-right area, with the summary line of the entry. Reading still shows the entries in the full-screen text block.

## Preload

`config/memory_preload.yaml` lists entries (each one with a `key` and a version per language) that are written to the long term memory at startup. An entry that is already there (by key and language) is not written again. A language that is missing is completed by the consolidation.

## The shutdown

`close_nicely` first stops the scheduler, then summarizes the conversation (`memory.summarize_on_close`) waiting at most `memory.summarization.close_timeout_seconds`. Before sending the summary, a copy of the raw conversation is written to `pending_conversations` as *in-flight*; the summarizer deletes it when it is done. If the summary does not finish (a busy Support worker, a slow LLM, a second Ctrl + C, a kill), the copy stays and the next start turns it into a normal pending conversation, for the consolidation. The systemd service gives 120 seconds to stop (`config/system/pitxu.service`).

## Operating it

```
poetry run util -u migrate_db            # apply the pending migrations now (also done at startup, with a backup)
poetry run util -u consolidate_memory    # run the consolidation now. With memory.consolidation.dry_run: True it only logs
poetry run util -u check_config          # compare the live config files with their .dist (or: make check-config)
```

- **Backups**: `storage/db/backups/`, named `pitxu-<group>-<label>-<date>.db`. The groups (`migration`, `consolidation`) are kept separately (`database.sqlite.backups_keep`, `memory.consolidation.backups_keep`), so the frequent ones do not push out the rare ones.
- **Restoring a backup**: stop the service, copy the backup over `storage/db/pitxu.db`, delete `pitxu.db-wal` and `pitxu.db-shm` if they exist, start the service.
- **Removing a forget request** by hand: `DELETE FROM short_time_memory WHERE id = <id> AND summary LIKE 'FORGET REQUEST%';`
- **A consolidation that crashed** leaves a lock in `memory_meta`. It is taken over when the process that held it is gone, or after `memory.consolidation.lock_ttl_seconds`.
- **Settings**: all of them are in `config/memory.yaml` (documented there) and `config/database.yaml`. A value that is not valid is reported in the log at startup and replaced by its default.

## Tests

`make unittests`, see [test/README.md](../test/README.md).
