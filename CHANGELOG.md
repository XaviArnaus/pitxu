# Changelog

## v0.4.2b - ??

### Fixed
- Fix partial merging when transcription end is cut and next does not correct it [#52](https://github.com/XaviArnaus/pitxu/pull/52)
- Fix UX not being prepared when user answers back too quickly [#54](https://github.com/XaviArnaus/pitxu/pull/54)

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