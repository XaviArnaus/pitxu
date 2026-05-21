# Changelog

## v0.3.5 - 2026-05-21

### Added

- Implement Whisper and Faster Whisper Speech-To-Text transcription engines [#31](https://github.com/XaviArnaus/pitxu/pull/31).
    - Prompt instructions to care about dates, times and memory saving success
    - New execution mode `local_status` that allows only local and the `/status` endpoint
    - Ability to download the content of a given URL and return it to the chatbot, as an external tool.
    - Ability to download the raw code from a Github url, as an external tool
- Pronounce correctly "Xavi" [#33](https://github.com/XaviArnaus/pitxu/pull/33).
- Warm up the Chatbot before the user interaction [#34](https://github.com/XaviArnaus/pitxu/pull/34)

### Changed

- Process names now are defined by the class identification method
- Chatbot Gemini main model is now be defined in the config
- Account for the STT processing time when identifying an ongoing conversation (avoid ignoring long trascriptions)

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