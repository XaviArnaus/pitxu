⚠️ Started on 2026-01-28, misses a lot

[ ] Show the ClassName in the logs.
[ ] Try to remove all wait_for_queue and rely only in wait_for_busy_flag
[ ] Mock correctly RawInputStream for Mic (fake the context!)
[ ] Mock correctly OutputStream for Speakers
[ ] Review idle mode (was: eyes!)
[ ] Thinking and Speaking effect should be bundled in the painter or the macros, and be set up as permanent callbacks, and control them from main (or else) via busy flags only.
[x] Add any alert from a remainder into the chatbot's history, so it remembers having done so.
[ ] Chatbot Historic: `Download > Filter >Store > Load` at a new session
[ ] Now the Eyes statics are done by Canvas, not loading a new Image (which forced a clear() in eInk). Review if still happens (LCD doesn't)
[ ] Parse the markdown answer and pick the **titles** on the bullet points, to present it in the screen while talking. 
        Identify which text (sentence?) is every sintetized chunk (sentence?), then I can now when each sentence is spoken.

## Tech debt found while reworking the reminders

Not part of the reminders work: to tackle later, each one by itself.

### `datetime` / `time` uses that could go through `Xtime`

The new `Xtime` helpers are `datetime_to_str`, `add_time` and `seconds_between`. Two more would cover several of these: `now_iso()` and `iso_to_datetime()`.

[ ] `db_sqlite.py:144`: `datetime.now().strftime(...)` for the backup names.
[ ] `lists.py:61,192`: `datetime.now().strftime(...)` (do it together with the Lists pass, like the Reminders).
[ ] `memory.py:151,186,221,331,394,717,728` and `memory_consolidator.py:110`: `Xtime.now().isoformat()` (10 times). New `Xtime.now_iso()`.
[ ] `memory.py:242`, `main.py:2391`, `json_logger.py:130`: `datetime.fromisoformat(...)`. New `Xtime.iso_to_datetime()`.
[ ] `memory.py:428`: `Xtime.now() - timedelta(...)`. `add_time`.
[ ] `memory.py:872`, `memory_consolidator.py:295`: `now.strftime('%A %Y-%m-%d %H:%M')`. `datetime_to_str`.
[ ] `json_logger.py:147,154`: `strptime` and `now().date()`.
[ ] `emoji_stats.py:71`, `system/time.py:33`, `system/date.py:40`: `time.strftime(...)` with the `time` module. `Xtime.current_time_str`.
[ ] `system/date.py:66-67`: `strptime` and `strftime`. `str_to_datetime` and `datetime_to_str`.
[ ] `dsi_lcd/device_wrapper.py:58`: `datetime.now().strftime(...)`.
[ ] `world/weather.py:97,162`, `main.py:2045`: `datetime.now().hour`. `Xtime.now().hour`.
[ ] `main.py:1010,1016,1108,1822,2365`: `datetime.now()` and `timedelta`. `now`, `add_time`, `seconds_between`.
[ ] `main_client_ptt.py:200,203,227,435,506,885`: `datetime.now()` and a `total_seconds()` difference. `now` and `seconds_between`.

### Busy-flag checks in `main.py` that are not `Interaction.is_interaction_busy()`

`is_interaction_busy()` is the four flags together (chatbot, speaker, transcriber, voice detected). These check a subset, each for its own reason. Review if some of them deserve their own helper in `Interaction`:

[ ] Chatbot and speaker only (idle mode starts when both are free, `main.py:2167` and `2324`). Candidate: `is_assistant_busy()`.
[ ] Transcriber or voice detected (the end of the countdown waits while the user speaks, `main.py:2265` and `2297`). Candidate: `is_user_input_busy()`.
[ ] Transcriber only (the early thinking effect and the holding bar, `main.py:517,525,530,1133,2274`).
[ ] Speaker plus config (speech interruption by the button, `main.py:1936`).

### Database naming

[ ] Rename the `reminders` table to singular `reminder` (and its index `idx_reminders_pending` to `idx_reminder_pending`) in a small migration, to match `short_time_memory`, `knowledge_base`, `list`... Remember to update `reminders.py`, the legacy import, docs and tests.
[ ] Same for `pending_conversations`, if we want full consistency.

### Lists

[ ] Let a list stay on the screen after the speech ends, until another paint claims the area (the painter already replaces a staying paint when a new one arrives). For now it shows only while speaking.
[ ] Highlight colours for added / updated / done items (the `MarkdownRenderer` has a single foreground colour and no strikethrough, it needs an extension).

### Stuck VAD flag

[ ] Cleaner fix: reset the voice-detected flag when the mic is muted, instead of ignoring it in `is_interaction_busy()` while muted.

### Found in the Gemini chat history

[x] `gemini_chatbot.py:305,368,387,405,418`: `record_history(...)` of the error paths gets `model_output=types.Content(...)`, but the library (google-genai 1.62) expects a list of `Content` and extends the history with it: a single `Content` adds tuples (`("role", "model")`...) to the comprehensive history. It is harmless for the curated history (those turns are not valid), but `get_chat_history_as_list_of_dicts(curated=False)` would fail on them. Wrap it in a list, like `add_notice_to_history()` does.
