# Reminders

The chatbot sets reminders for a date and time, and Pitxu announces them out loud (and on the screen) when the time comes. They are in the SQLite database (`storage/db/pitxu.db`, table `reminders`, created by the migration `0004`). Before that they were in `storage/reminders.yaml`: see [the old file](#the-old-file).

## A reminder

| Column | What it is |
| --- | --- |
| `id` | What identifies it, like the memory entries. Several reminders can share the same date and time. |
| `due_at` | Local date and time, `YYYY-MM-DD HH:MM` (it is compared as text, so it orders by time). |
| `text` | What to remind, in the language it was set. |
| `language` | The language of the session where it was created. |
| `created_at` | When it was created. |
| `announced_at` | When it was announced. Empty while it is pending. |

An announced reminder is **not deleted**: it stays `announced_at` days (`reminders.keep_announced_days`, 7 by default) and the night tasks delete it afterwards. Meanwhile the chatbot can still ask about it, and moving it makes it pending again (a snooze).

## What the chatbot can do

Every tool answers with the reminder as a dict (`id`, `date`, `time`, `text`, `announced`), or with a message in the language of the session when something is wrong.

| Tool | Does |
| --- | --- |
| `create_reminder(date, time, reminder_text)` | Creates it and gives the `id`. |
| `get_reminders_for_date(date)` | The ones still pending of a day, in time order, with their `id`. |
| `get_reminder(reminder_id)` | One reminder, also if it was announced (`announced` tells). |
| `update_reminder(reminder_id, new_text)` | Changes the text. |
| `move_reminder(reminder_id, new_date, new_time)` | Changes the date and time, and gives `previous_date` and `previous_time`. |
| `delete_reminder(reminder_id)` | Deletes it and gives what was deleted. |

The date and the time are checked and normalized (`2026-1-5` is `2026-01-05`, `9:05` is `09:05`), and a date and time in the past is refused. An invalid one, or an id that does not exist, gets its message.

On the screen the tools show the result localized: what was set, deleted, updated or moved, or how many reminders a day has.

## The announcement

Reminders are **not looked up by the exact minute**: every minute (and every second while waiting, see below) Pitxu asks for everything pending whose time has come. So one that was due while Pitxu was busy, or off, is announced as soon as it can.

- **Several at once are one announcement**, spoken and shown as a list: "You have 3 reminders: …".
- **A late one says when it was for**: "Reminder: At 14:20, buy milk." after `reminders.late_after_minutes` (2 by default). From another day it says the date too.
- **A very old one** (after `reminders.very_old_after_hours`, 24 by default) says the date and warns: "This reminder is very old and could not be announced back then."
- **It waits while Pitxu is busy**: while the user speaks, the speech is transcribed, the chatbot answers or the speaker speaks (`Interaction.is_interaction_busy()`) nothing is announced. The log says "waiting for Pitxu to be idle", and the every-second tick announces them as soon as it is idle, in its own job so the countdown and the fans keep going. There is no limit to the wait.
- **Marked as announced after the speech.** If the application dies while speaking they are announced again at the next start. If the speech fails, they are marked anyway, otherwise it would fail again every minute (see the log: "Error announcing the reminders").
- **Afterwards the turn goes back to the user** (the microphone listens, and the hold time restarts), except when only the wake up button is wanted: then the microphone stays muted.

The PTT client keeps its own simpler announcement, one by one.

## Pitxu remembers it

When the announcement was said:

- It goes to the **chatbot history**: a user turn that starts with `[SYSTEM NOTICE]` (it is not the user speaking) saying that the application announced the reminders with these ids, and the spoken text as the model turn. The chatbot can answer "did you tell me to check the oven?" in the same session, and move or delete the reminder by its id.
- It is saved as a **short term memory entry**, also when the user says nothing afterwards: "Reminder announced: check the oven", or "3 reminders announced". The content has the time, what was said and the ids. It is consolidated like any other entry, so it can be found in the next sessions.
- The notices **do not count as the user speaking** when deciding if a conversation is worth summarizing, and the summary prompt knows them: they are not duplicated in the summary, and a conversation with only notices is not significant. What the user does about a reminder (moves it, deletes it) does go into the summary.

## Languages

Every message is in `language.reminders.*` in the four languages. A language change restarts the application (exit code 42): the reminders are in the database, so they survive it, and the ones that came due meanwhile are announced late when it is back. The text of a reminder stays in the language where it was created; the words around it ("Reminder:", "At 14:20, …") are in the current one.

## Settings

All in `config/main.yaml`, block `reminders`. A value that is not valid is reported in the log and replaced by its default, like the memory settings (`poetry run util -u check_config` compares the live file with the `.dist`).

| Setting | Default | What it does |
| --- | --- | --- |
| `reminders.keep_announced_days` | 7 | Days that an announced reminder is kept before the night tasks delete it. |
| `reminders.late_after_minutes` | 2 | Minutes after its time from which the announcement says when it was for. |
| `reminders.very_old_after_hours` | 24 | Hours after its time from which it also warns that it is very old. It should be longer than the late time. |

## The old file

At startup, right after the migrations, if `storage/reminders.yaml` exists its reminders are moved into the database: all of them, also the ones in the past (they are announced as late or very old). The file is **deleted only when every reminder is in the database**; if one cannot be read, the file stays, the log says which, and the next start tries again without duplicating what is already there.

## When something looks wrong

- "Could not get the due reminders" in the log: the database could not be read. Reminders are announced again as soon as it can.
- "waiting for Pitxu to be idle" and nothing is announced: a busy flag may be stuck. The reminders are announced when it clears.
- A reminder never rang: look at its row. If `announced_at` is set it was announced (or its speech failed, see the log); if `due_at` is in the future it is not due yet.
- `poetry run util -u migrate_db` applies the migrations by hand.
