# Changelog

## v0.4.2b - ??

### Added

- Memory in two levels. Everything new lands in the **short term memory**; every night it is consolidated by an LLM into the **long term memory** (read-only for the chatbot, one entry per language: en, es, ca, de). The chatbot searches both, short term first, with `S:` / `L:` ids. See [docs/memory.md](docs/memory.md).
- The chatbot can correct a long term entry (saved as a correction that is applied overnight) and ask to forget one (registered, never applied: the long term memory is only changed by the consolidation).
- Summary of the conversation also when the application closes (exit words, SIGTERM, shutdown, reboot...), with a write-ahead copy so it is not lost if the summary does not finish. "No significant conversation" is a valid outcome.
- Tool `remember_this_conversation` to ask for the conversation to be remembered.
- Versioned database migrations, applied at startup with a backup first; backups of the database before every consolidation.
- Write protection of the long term memory in the database itself for everything that is not the consolidation.
- Validation of the memory settings at startup (a wrong value is reported and replaced by its default), and `util -u check_config` to compare the live config files with the `.dist`.
- The chatbot uses the memory on its own (`chatbot.memory_autonomy`): it saves what is worth keeping without asking or announcing it, and searches before answering. What it writes is notified in the top-right area with the summary line, instead of the full screen.
- The memory search is by keywords (title and content, any word, ranked) in both memories, so natural queries find the long term entries too.
- When the chatbot understands that the user ends the conversation, Pitxu says a random ending sentence by itself (`language.end_of_conversation_answers`) and goes idle right away, without waiting for the hold time. The exit words still close the application. The status area shows "Conversation ended" and "Summarizing conversation".
- Reminders are in the database (migration 0004; see [docs/reminders.md](docs/reminders.md)) and are identified by an id, like the memory entries: several can share the same date and time, and the chatbot tools read, update, move and delete by `reminder_id`. A reminder that was announced is kept for `reminders.keep_announced_days` (7), and moving it makes it pending again. The reminders of the old `storage/reminders.yaml` are moved into the database at startup, and the file is deleted only when all of them are in.
- The DSI screen dims when the app goes into idle mode and recovers its brightness when it wakes up (`dsi_lcd.idle_dimming`: `enabled`, `brightness_percent`, `active_percent`). The brightness is also restored at startup and when the app closes. It uses the panel's `brightness` in sysfs, independent from the screen on/off command.
- Test suite in `test/` (`make unittests`). The scripts for the sound hardware moved to `test/hardware/`.

### Changed

- Pitxu remembers what it announced: every announcement of reminders is added to the chatbot history (a marked system notice with the reminder ids, and what was said), so it can answer "did you tell me to check the oven?" and move or delete the reminder by its id; and it is saved as a short term memory entry, also when the user does not react. The system notices do not count as the user speaking for the conversation summary, and the summary prompt (in the 4 languages) knows them.
- The announcement of the reminders: all the ones due at the same time are one announcement, spoken and shown as a list; a late one says when it was for ("At 14:30, ..."); one that is very old (24 hours by default) says the date and warns that it could not be announced back then; and nothing is announced while Pitxu is answering, speaking or listening: it waits and announces as soon as it is idle. New settings `reminders.late_after_minutes` and `reminders.very_old_after_hours`. (The PTT client keeps announcing one by one.)
- After announcing reminders Pitxu goes idle right away (as when a conversation ends), whatever the wake up method: the speaking effect stayed on screen with the wake up button only, and an open microphone could take the TV for the user. A reply needs the trigger words or the button (the announced reminders are in the chatbot history, so it can move or delete them). The reminders stay on the screen for `reminders.screen_hold_seconds` (5; 0 to turn it off) after being said, with a smile and a bell (`animations.reminder`), and Pitxu goes idle after that (not if somebody woke it up meanwhile). Text and animation live by a new shared flag, `ANNOUNCEMENT_BUSY`, raised and lowered by the announcement (`Interaction.show_arbitrary_text_on_foreground_while_announcing()` and `show_animation_while_announcing()`, like the speaking ones, reusable for any notification that Pitxu starts by itself), independent of the speech and the mouth. A list of reminders has the title "Reminders" (`language.reminders.reminder_screen_title`) above it.
- The reminders that are due are announced also when their minute was missed (a busy Raspberry, a restart): they are not looked up by the exact minute anymore, and the purge of the past reminders at startup is gone.
- Removed the message `reminder_already_exists` (it could never happen), and `reminder_not_found` now tells the id.
- The memory preload entries have a `key` and a version per language.
- The closing waits for the conversation summary (bounded by `memory.summarization.close_timeout_seconds`), and the systemd service has `TimeoutStopSec=120`.
- Signals (SIGTERM, SIGINT) only ask the run loop to close; a second one stops waiting for the summary.
- An empty answer of the chatbot after a successful end of conversation tool is not an error anymore (no retries, no error message, no sad face). The tool and its result are defined once in `SystemConversationFlow`, and used by the chat response and the reactions.
- Removed the unused settings `memory.filename` and `memory.summary_similarity_threshold`.

### Fixed
- Fix partial merging when transcription end is cut and next does not correct it [#52](https://github.com/XaviArnaus/pitxu/pull/52)
- Fix UX not being prepared when user answers back too quickly [#54](https://github.com/XaviArnaus/pitxu/pull/54)
- Reminders: the date and the time are normalized (`9:05` and `2026-1-5` were accepted but never rang), a reminder in the past is refused with its message (it was accepted and never rang), and what the screen shows about the reminders is localized (the count was in English, and the deleted, updated and moved messages were not used).
- The history of the chatbot after an error: the model turn that is recorded was a single `Content` where the library expects a list, so the full history got tuples (`("role", "model")`...) instead of the turn.
- The day of the week: the chatbot guessed it wrong ("Sunday" on a Monday) because the date tool gave only `2026-11-23`. `get_local_system_date()` now returns `2026-11-23 (Monday)` and the prompts (4 languages) tell to use it and never calculate it. The English name comes from the new `Xtime.weekday_name()`, which does not depend on the locale of the system, and the memory prompts use it instead of `%A`.
- Reminders waiting for Pitxu to be idle for no reason: with the microphone muted (wake up by button) the VAD flag could stay up for ever (it is only cleared when the input stream runs again), and it counted as an interaction. It does not count while the microphone is muted, and the log of the wait says which flags are up. The countdown is cleared when the reminders are announced, so it does not stay under them.
- Sound right after the countdown reached 0% kept the countdown and the listening animation on screen during the whole transcription, and with nobody waiting for an answer. With only the wake up button wanted, the microphone stops at the 0% itself (its cleanup follows in the next second as before); in the voice modes the microphone stays open for the trigger words, and speech that starts after the 0% is idle speech: the countdown ends and it is transcribed like any other. Speech that started before the 0% still delays the end. The countdown tick is now its own method (`_tick_interaction_countdown`), covered by tests.
- The transcriber process never received the audio parameters, so its Preprocessor logged `None` for the filter frequencies, order and samplerate (the filters used their built-in defaults, which equal the usual config values). They are sent now.
- Summary of the conversation at its end unreliable, and the summarizer failing on edge cases (invalid JSON, quota, network).

## v0.4.2b - 2026-11-16

### Added

- Wake up through a physical button [#43](https://github.com/XaviArnaus/pitxu/pull/43)
- Status area in the DSI LCD that displays log messages, and Status Buttons [#47](https://github.com/XaviArnaus/pitxu/pull/47)
- Interrupt the speech with a button [#49](https://github.com/XaviArnaus/pitxu/pull/49)
- Shared Memory Monitor thread that manages flag changes.
- Dynamic Stability threshold to commit partial words with a longer buffer for longer inputs.
- Animations cache and lazy loading [#45](https://github.com/XaviArnaus/pitxu/pull/45)
- Real KITT mouth effect while speaking [#44](https://github.com/XaviArnaus/pitxu/pull/44), animated THINKING state [#50](https://github.com/XaviArnaus/pitxu/pull/50) and a blue networking effect.
- Centralised gathering of device values (battery, volumes, temperature, fans) in the `DeviceMonitor` [#48](https://github.com/XaviArnaus/pitxu/pull/48)
- Log entries tell the class that raised them.
- Configurable initial Mic volume.

### Changed

- Iterated the UX [#35](https://github.com/XaviArnaus/pitxu/pull/35)
- Partial transcriptions are merged using a Timestamp-based Append, to avoid re-adding already processed words [#42](https://github.com/XaviArnaus/pitxu/pull/42)
- General iteration to improve responsiveness [#46](https://github.com/XaviArnaus/pitxu/pull/46)
- Threaded input stream removed and input wrapped in a class.
- Painter and Macros relocated and generalised, display areas defined by intention.
- Legacy displays (Canvas V1, eInk, LCD, matrix LED) moved to `lib/legacy/` and loaded lazily. `lib/ups` retired in favour of the `DeviceMonitor`.
- Reduced the Github tools to avoid chatbot misconceptions, and paginated the files of a PR.
- Cleaner shutdown: the main process closes everything in order, children exit after `finish`, and no more broken pipes nor leaked semaphores.
- Unused imports, dead modules and tracked compiled files removed.

### Fixed

- 100% CPU spin in the input stream and input samplerate issues.
- Battery level blank on transient I2C read errors.
- Idle screen keeping the top-right panel after the timeout.
- Google Search and Maps tools in the RPi (language), Github code retrieval and sending mails.
- Memory summarisation missing the API key.

## v0.4.1 - 2026-06-04

### Added

- FasterWhisperStream delivers also partials.

### Changed

- Control STT via a new State Machine [#41](https://github.com/XaviArnaus/pitxu/pull/41)
- Simplify the callback to be used by RawInputStream and decouple the logic by using a queue to a new Thread that does the VAD distribution.
- Embed the RawInputCallback in a Thread (not sure if it does anything)

### Fixed

- Some states where incorrectly fit.


## v0.4.0 - 2026-06-02

### Added

- Implement Streaming / Sliding Window into FasterWhisper [#36](https://github.com/XaviArnaus/pitxu/pull/36)
- Improve Github tool capabilities
- Add retries into the summarizer
- Added a Shared Memory Values space like the Flags.

### Changed

- Iterate the chatbot prompt to avoid using so many tokens
- Big iteration on closing instances / processes to try to smooth the app ending
- Some visual improvements, like in tool callbacks.
- SQLite3-based memory approach, replacing file-based one [#40](https://github.com/XaviArnaus/pitxu/pull/40).

# Fixed

- Fix memory update not returning the entry
- Fix memory migration util
- Fix trigger words identification

## v0.3.5 - 2026-05-22

### Added

- Implement Whisper and Faster Whisper Speech-To-Text transcription engines [#31](https://github.com/XaviArnaus/pitxu/pull/31).
    - Prompt instructions to care about dates, times and memory saving success
    - New execution mode `local_status` that allows only local and the `/status` endpoint
    - Ability to download the content of a given URL and return it to the chatbot, as an external tool.
    - Ability to download the raw code from a Github url, as an external tool
- Pronounce correctly "Xavi" [#33](https://github.com/XaviArnaus/pitxu/pull/33)
- Warm up the Chatbot before the user interaction [#34](https://github.com/XaviArnaus/pitxu/pull/34)
- Add Ability to pull content from Github PR and branches [#37](https://github.com/XaviArnaus/pitxu/pull/37)
- Add name variations to improve the waking up by triggering words [#38](https://github.com/XaviArnaus/pitxu/pull/38)

### Changed

- Process names now are defined by the class identification method
- Chatbot Gemini main model is now be defined in the config
- Account for the STT processing time when identifying an ongoing conversation (avoid ignoring long trascriptions)
- Change the name from Gina to Teresa to improve the STT recognition as Trigger Word.
- Pronounce correctly "Xavi", second iteration [#39](https://github.com/XaviArnaus/pitxu/pull/39)

### Fixed

- Missing Greetings per time of the day texts in configs
- JSON Logger naming configurations
- Shudown, Reboot and Restart did not work

## v0.3.4 - 2026-05-10

### Added

- Long Term Memory, initial implementation [#30](https://github.com/XaviArnaus/pitxu/pull/30).
    - New Code Generation visualization while speaking
    - New Text block visualization while speaking

### Changed

- Greeting is sensible about the time of the day

### Fixed

- Code extraction for visualization

## v0.3.3 - 2026-04-30

### Changed

- Replace Infinite Loop approach with VAD Callback approach [#29](https://github.com/XaviArnaus/pitxu/pull/29).

## v0.3.2 - 2026-04-30

### Added

- Speech-To-Text Pre-Process [#27](https://github.com/XaviArnaus/pitxu/pull/27), [#28](https://github.com/XaviArnaus/pitxu/pull/28).

## v0.3.1 - 2026-03-07

### Added

- Push-To-Talk HTTP Client [#25](https://github.com/XaviArnaus/pitxu/pull/25), [#26](https://github.com/XaviArnaus/pitxu/pull/26).
- Handle Code Answers graphically [#24](https://github.com/XaviArnaus/pitxu/pull/24)
- Case Fans control [#21](https://github.com/XaviArnaus/pitxu/pull/21), [#22](https://github.com/XaviArnaus/pitxu/pull/22)
- Lists feature [#20](https://github.com/XaviArnaus/pitxu/pull/20)

## v0.3.0 - 2026-02-09

### Added

- All support for the *DSI 5"* screen with *USB Soundcard* over *SSD USB3* disk.

## v0.2.0

### Added

- All support for the Whisplay all-in-one card support. Includes display rework to migrate from *eInk* + *LED 8x8 matrix* to 1 single display merged as *ForegroundDisplay* and *BackgroundDisplay* respectively

## v0.1.0

### Added

- Initial development for double screen *eInk* + *LED 8x8 matrix*, *USB Soundcard* and *SD Card*