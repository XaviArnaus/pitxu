# Pitxu
Chatbot project over Raspberry Pi 5 in Python.

The intention is to have it 100% offline, the current status is:

- Speech To Text:
    - Offline
    - 3 engines implemented, the user can choose via config file:
        - **Vosk** (small model): Fast, transcription per audio chunk, pretty inaccurate (and frustrating).
        - **Whisper**: (tiny model): Slow (frustrating), transcription in one shot (as opposite from per chunks), accuracy is very good.
        - **Faster Whisper** (tiny model): Somewhere in between (feels slow), transcription in one shot (as opposite from per chunks), accuracy is very good.

- Chatbot:
    - Online
    - engines can be defined in the config:
        - Gemini 2.5 Flask: Fast, fails often due to high demand and has intermitent problems with external tools.
        - Gemini 3.1 Flash Lite: Slower on warm up, but pretty fast at low demand moments. Thinking is better, and has less issues with external tools.

- Text To Speech:
    - Offline
    - Uses **Piper**: Voices are downloaded in the repository, fast, no-streaming mode. The quality depends on the model.

🚨 **This is a Work in Progress project. Take it or leave it. Suggestions are welcome.**

# Installation

To install into a Raspberry Pi 5 read the guide here:
[Install Pitxu in a Raspberry Pi 5](./docs/INSTALL_RPI5.md)