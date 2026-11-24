# Lists

The chatbot keeps lists (shopping, to do...) and their items. They are in the SQLite database (`storage/db/pitxu.db`, tables `list`, `list_item`, `list_translation` and `list_item_translation`, created by the migration `0005`). Before that they were in `storage/lists.yaml`: see [the old file](#the-old-file).

## Lists and items

| Table | What it holds |
| --- | --- |
| `list` | `id`, `name`, `name_key` (the name without accents, capitals or extra spaces), `language` (of the name and the description), `description`, `favourite`, dates, `deleted_at`. |
| `list_item` | `id`, `list_id`, `text`, `text_key`, `language`, `done`, `done_at`, dates, `deleted_at`. |
| `list_translation` | The name and description of a list in another language. |
| `list_item_translation` | The text of an item in another language. |

- **Lists are told by name, items by id**, like the reminders and the memory entries. The chatbot gets the ids from `get_lists`.
- **A name, or an item text, can't be twice** (among what is not deleted), compared without accents, capitals or extra spaces, **in every language it is stored in**. For an item, being done or not does not matter: it is the same item.
- **Deletes are soft** (`deleted_at`): a deleted list or a removed item is in the trash, and `restore` brings it back. A deleted list hides its items but does not touch them. See [the night cleanup](#the-night-cleanup).
- **Items come open first, then done**, each group by creation order. The screen and the answers use that same order.

## What the chatbot can do

The answers are compact, to cost few tokens: an item is `[id, text, done]` (`[id, text]` when just added), and a list that was changed is not read back (the screen reads it from the database). A problem is a message in the language of the session. The 9 tools, with about 400 words of descriptions in total:

| Tool | Does |
| --- | --- |
| `get_lists(list_name=None, language=None)` | Without a name: the lists with `id`, `name`, `open`, `done` and `favourite`. With a name: that list with its `items`. With a `language` the texts come in it, and `untranslated` counts what is not translated yet (the chatbot translates it). |
| `create_list(name, copy_from=None, items=None)` | Creates a list, with its items. If it exists, nothing is created (`created` false). With `copy_from` it gets that list's description and items, all open again: a new list from a previous one in one shot. |
| `update_list(list_name, new_name, new_description, favourite)` | Renames it, changes its description, or marks it as favourite. The items are not touched. |
| `delete_list(list_name)` | Deletes it (to the trash). It needs an exact, or really similar, name. |
| `add_items(list_name, items)` | Adds several items at once. An item that is already there is not added: it comes in `duplicates` as `[id, text, done]`, and the chatbot tells the user and, if it is done, offers to mark it open again. Nothing is reopened by itself. |
| `update_item(item_id, new_text)` | Changes a text. If another item has it, nothing changes and it comes as `duplicate`. |
| `check_items(done, item_ids=None, list_name=None)` | Marks items as done, or open again. Either some ids or a list name for all its items (to reset it), never both. |
| `remove_items(item_ids)` | Removes items (to the trash). |
| `restore(item_ids=None, list_name=None)` | Brings back removed items by id, or a deleted list by name. With the name of a list that exists and no ids it only gives its removed items, so the chatbot can ask which one. |

A list that does not exist is **not created by an add**: the answer lists the lists that exist and tells the chatbot to use `create_list` (it does it without asking, see [the prompt](#the-prompt)).

### Finding a list by its name

The name comes from a transcription, so it is looked up in this order: the exact name (in any language), a unique partial one (all the words of one are in the other: "shopping" for "Shopping list"), and the most similar one. If several are equally good it is an ambiguity: the tool answers with the candidates and the chatbot asks. **A delete is stricter**: only the exact name or a really similar one; "shopping" does not delete "Shopping list", it answers with the lists that exist.

## On the screen

The list shows while Pitxu speaks (it goes away with the speech; staying longer is in `TODO.md`). The screen text is **plain text**, so the status and the change are told with emoji: `⬜` open, `✅` done, `👈` at the end of the items that the last action touched (added, changed, marked, restored, or the one that was already there when an add was refused), and a last line `🗑 Removed: milk`. A favourite list has `⭐` instead of the usual `📝`, also in the list of lists, where each line has the number of open items. A list of more than 8 items is a window around the first one touched, with `… +n` for the hidden ones.

The list is read from the database when it is shown, in the language of the session, so it costs the chatbot no tokens.

## Languages

Every text has a language (the one of the session where it was written) and the night translation gives it a version in the other supported languages (`app.supported_languages`): names, descriptions and items. Reading in a language gives the translation, or the original if it is not translated yet.

- **The night translation** (`ListTranslator`, run by the Support worker after the night tasks start) asks the LLM, in batches, for what is missing. What fails stays missing and is tried the next night. `poetry run util -u translate_lists` does it now. It reads the `lists.translation` settings, with its own model and retries (it does not read any memory setting).
- **The language of a text is only a hint**: dictating a German shopping list in an English session works, the LLM leaves what is already in a target language as it is.
- **Editing a text deletes its translations**, and the night makes them again. A translation that arrives for a text edited meanwhile is thrown away.
- **Duplicates are looked up in every language**: "milch" is the same item as "milk" once translated.
- **To print or send a list in another language** the user says it ("print this shopping list in German"): the chatbot reads it with `get_lists(list_name, language)` and translates what comes as `untranslated`. Without a language it uses the current one.

## The night cleanup

Two stages, in the night tasks, with these settings:

1. Items marked as done more than `lists.cleanup.done_after_days` (14) ago **go to the trash**, unless their list is a favourite: a favourite list keeps its done items. They can be restored.
2. What is in the trash for more than `lists.cleanup.trash_after_days` (30) days **is deleted for good**: removed items, and deleted lists with their items and translations. An item trashed by the first stage has the whole period from that night.

## The prompt

`chatbot.lists_instruction` (in `chatbot.yaml`) is added at the end of the system instruction, in English for every language, like the memory one. It tells the chatbot to do what is asked without confirmation, put several items in one call, create a list that does not exist, mark as done instead of removing, tell about duplicates in one sentence, not read the list aloud, use ids from `get_lists`, and translate what is `untranslated` to print or send in another language. Empty it to add nothing.

## Settings

All in `config/main.yaml`, block `lists`. A value that is not valid is reported in the log and replaced by its default (`poetry run util -u check_config` compares the live file with the `.dist`).

| Setting | Default | What it does |
| --- | --- | --- |
| `lists.cleanup.enabled` | True | False: no cleanup. |
| `lists.cleanup.done_after_days` | 14 | Days that a done item stays in its list. |
| `lists.cleanup.trash_after_days` | 30 | Days that the trash keeps what is in it. |
| `lists.translation.enabled` | True | False: nothing is translated. |
| `lists.translation.batch_size` | 30 | Texts sent to the LLM at once. |
| `lists.translation.model` | gemini-3.1-flash-lite | The model. Empty: the default of the code. |
| `lists.translation.retries` | 3 | Tries of a request. |
| `lists.translation.backoff_seconds` | 5 | Seconds before the second try (doubles after each). |
| `lists.translation.request_timeout_seconds` | 60 | Seconds before a request gives up. |
| `lists.translation.max_total_seconds` | 180 | Seconds that the tries of a batch can take altogether. |
| `lists.translation.prompt` | | What the LLM is asked. It must have a `%s` where the texts go. |

The messages are in `language.lists.*`, in the four languages.

## The old file

At startup, right after the migrations, if `storage/lists.yaml` exists its lists are moved into the database, with their creation dates and the language of the application. An item that is twice in a list is imported once (the repeated ones are in the log). The file is **deleted only when every list and item is in the database**; if something cannot be read the file stays, the log says what, and the next start tries again without duplicating what is already there.

## When something looks wrong

- A list in another language is shown untranslated: the night translation did not run yet, or failed (see the log: "Lists translation"). `poetry run util -u translate_lists` runs it.
- The chatbot says it cannot find a list: the answer lists the ones that exist. A name that matches several lists is an ambiguity, and the chatbot asks.
- Something is missing from a list: look in the trash, `restore(list_name=...)` shows what was removed.
- `poetry run util -u migrate_db` applies the migrations by hand.
