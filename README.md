# pitxu
Chatbot project over Raspberry Pi (5 / Zero 2w)

🚨 **This is a Work in Progress project. Take it or leave it. Suggestions are welcome.**

# Install

This project works with a bunch of system resources. This means that for Python to be able to
compile the dependecies we need to have some packages in the OS level.

⚠️ Due to the Text-to-Speech (at least), the linux system must be 64 bits. This is choosen when burning the new Raspberry Pi OS image using the official Imager. Make sure that you choose a 64bit distro.

## Linux (Raspberry Pi)

### To install dependencies in the OS-bundled python: `python3-pip`

To use Pitxu without Poetry we need to install the dependencies for the Python bundled in the OS (that must already be 3.11 min).
This is only in case you want to avoid using Poetry, as in the Raspberry Pi we don't need to have virtual environments (because you don't use that RPi for anything else, right?).
Please have the `python3-pip` pachage installed beforehand:

|⚠️ WARNING! DO NOT USE|
|--|
|Modern OS/Python are pointing out the difference between having Python budled to support internal applications, not for the end user. That's why we should always use a Virtual Environment. Keeping it here for knowledge sharing, but should not be used.|

For Debian based linux distros:
```
sudo apt install python3-pip
```

### Dependency in general to build other dependencies: `python3-dev`

Some dependencies are built at installing time. Please have the `python3-dev` pachage installed beforehand:

For Debian based linux distros:
```
sudo apt install python3-dev
```

### Dependencies related to `Pillow`

This is needed for the internal Pillow support, for the e-Ink display

For Debian based linux distros:
```
sudo apt install libjpeg-dev zlib1g-dev libfreetype6-dev
```

### Dependencies related to `Gemini`

This is needed for the internal Gemini support, for the dication feature

For Debian based linux distros:
```
sudo apt install libffi-dev
```

### Dependencies related to `pyaudio`

This is needed for the internal Pyaudio support, for the audio support

For Debian based linux distros:
```
sudo apt install portaudio19-dev python3-pyaudio
```

### Dependencies related to `lgpio`

This is needed for the internal GPIO support

For Debian based linux distros:
```
sudo apt install swig liblgpio-dev
```

### Dependencies related to `i2c`

This is not needed for the Python / Poetry application to work, but it's useful to debug and identify the own hardware.

For Debian based linux distros:
```
sudo apt install i2c-tools
```

### ❗️ All Linux/Debian dependencies in one line
Just make sure that I did not forget to add here anything from above. Just put them all together.

```
sudo apt install python3-dev libjpeg-dev zlib1g-dev libfreetype6-dev libffi-dev portaudio19-dev python3-pyaudio swig liblgpio-dev i2c-tools
```


## Mac OS

### Dependencies related to `pyaudio` and `sounddevice`

This is needed for the internal Pyaudio support, for the audio support

```
brew install portaudio
```

## Clone the repo and move yourself in

```
git clone git@github.com:XaviArnaus/pitxu.git
cd pitxu
```

## Install Poetry

```
curl -sSL https://install.python-poetry.org | python3 -
```

Remember that after the installation, most likely you need to add an `export` line in your shell config file (for example `/home/username/.bashrc`). The end of the Poetry installation announces that.

## Ininitalize the project

```
make init
```

## Notes regarding the Python dependencies installation

In lot of cases, poetry builds the dependencies and they fail due to diverse issues.

Warning: Apparently I could evolve all of this to leave the 2 packages below inside the `pyproject.toml`, so maybe try first to do the normal install and then jump directly to the 
installing packages in the shell. `Numpy` and `Onnxruntime` should be installed:
```
numpy = [{version="^2.3.4", markers="sys_platform=='darwin'"}]
onnxruntime = [{version="^1.23.2", markers="sys_platform=='darwin'"}]
piper-tts = [{version="^1.3.0", markers="sys_platform=='linux'"}]
```
... because would be very great to know a way to force "--no-deps" for a darwing marker there inside.

### Numpy
Numpy is a dependency from Piper. It is also mentioned in one of the Vosk (STT) examples as a tool for calculation.
I have it as a direct dependency as it gave some headaches. At the end, it gets installed but needs **VERY MUCH TIME**.
It's installation (isolated back then with `poetry add numpy -vvv`) was monitored with another ssh window running `htop`,
And it only worked after a reboot and directly install it.

### Onnxruntime
Onnxruntime is a dependency from Piper. It is needed for the TTS as controlls the model. It simply does not get installed
due to the `--no-deps` param in the section below. Needs to be installed by `poetry add onnxruntime -vvv`.


## Install packages that fail with Poetry

Some packages are found in the repository but will fail installing, for diverse reasons.

The workaround is to enter into the shell of the Poetry's virtual environment and `pip3 install` the packages there.
In general, the idea is that then they don't get compiled but rather it uses the _wheel_

ℹ️ It affects `gpiozero` & `piper-tts`, apparently only with Mac OS.

### ⚠️ Since Poetry (2.0.0), the shell command is not installed by default.
Then, install the `shell` plugin:

```
poetry self add poetry-plugin-shell
```

ℹ️ Added the plugin as a requirement in `pyproject.toml`, maybe this manual plugin installation is not needed now.

... and then you can continue as usual:

```
poetry shell
pip3 install gpiozero 
pip3 install piper-tts --no-deps
```

## Create a config file

```
cp config/main.yaml.dist config/main.yaml
```

... and edit it at your test

## Create an environment variables file

```
nano .env
```

... and add there your Google Gemini key, that you got for free from https://aistudio.google.com/app/apikey like

```
API_KEY=abcdefghijkl
```

You can also add here the credentials for sending emails through a Gmail account. You have to previously activate 2-step verification and add Pitxu as a new App Password, and then use this password instead of the account's one.
```
EMAIL_USERADDRESS=bob.pitxu@arnaus.net
EMAIL_USERNAME=bob.pitxu@arnaus.net
EMAIL_PASSWORD=patati patata
```


# Run

```
make run
```

# Current issues

## In RPi 02W, is mega slow.
No more to say. Not usable. Will bring data.

## RPi5 8GB
Works very decent, no very significant difference with MacOS

### Power
- Be sure to feed the RPi. Old USB chargers do not work. When charged the Piper model used to die by hunger.

### Sound
- From Piper 1.2.0 to 1.3.0 the API for `sintetize_stream_raw()` changed to `sintentize()` and the subsequent loop a bit as well.
- I did lot of tinkering in the underlying Linux (Debian/RaspberryOS) system to make the sound to work (ALSA, USB dongle, PulseAudio) that I don't know what actually makes it to play and record. I've dropped some test commands in [/bin](./bin/) for the next time. I remember that I deactivated the sound from the boot/ `config.txt`, in a wish to properly select the output device to the USB Audio.
- Some cricks and noise mostly at the beginning and at the end of the play

### Display
- Must activate the SPI interface from `sudo raspi-config`. 
- Getting very stuck with the display saying `waveshare_epd.epd2in13_V4 e-Paper busy` ... 
    - Check malfunctioning cables, faulty in-between pieces (GPIO HATs and headers). Happened to me twice.
    - Has plenty of problems controlling the subprocess to close properly, not allowing the next one to succeed. Complains about GPIO being busy while initialising the next Process. Solution was to move to a long lasting subprocess like Piper.
- Most of the times, the very first start, the Splash screen is shown grey-ish.

### Led Matrix
- Works good in general
- The very first show of the KITT mouth is shown mangled. The rest of the times is good.
- Spotted few times where the KITT mouth did not appear while TTS speaks. Smells like Shared Memory Flags were not updated on time.


# Ideas

- API public transport
- Button to mute, so it does not attend what is spoken in front
- Button to skip what is being TTS, so user can discard the explanation (can be anoyingly long)

Python offers several powerful libraries for sentiment analysis. Some of the most popular and effective ones include:

*   **NLTK (Natural Language Toolkit)**: A comprehensive library for natural language processing, NLTK includes tools for sentiment analysis, notably the VADER (Valence Aware Dictionary and Sentiment Reasoner) sentiment analyzer, which is particularly effective for social media texts.
*   **TextBlob**: Built on top of NLTK, TextBlob is known for its simplicity and ease of use, making it ideal for beginners and quick sentiment evaluations. It provides a pre-trained sentiment analyzer and offers fine-grained polarity scores and subjectivity analysis.
*   **VADER (Valence Aware Dictionary and Sentiment Reasoner)**: Specifically designed for analyzing sentiment in social media and short text content, VADER is a rule-based sentiment analysis tool. It generates compound polarity scores and can handle informal language, slang, and emojis.
*   **SpaCy**: A modern NLP library focused on efficiency and production use, SpaCy includes support for sentiment analysis. It utilizes a machine learning approach based on convolutional neural networks, which can handle complex language features like negation and sarcasm.
*   **BERT (Bidirectional Encoder Representations from Transformers)**: A state-of-the-art library from Hugging Face, Transformers offers a wide range of pre-trained models, including BERT, which achieve remarkable performance on sentiment analysis benchmarks.
*   **Flair**: Another advanced library offering sophisticated features and capabilities for more complex sentiment analysis tasks, including strong multilingual support.
*   **Scikit-learn**: A popular machine learning library, Scikit-learn includes tools for building custom sentiment analysis models using classifiers and feature extraction.
*   **PyTorch**: A deep learning framework used for building custom sentiment analysis models, PyTorch provides full flexibility to design and train neural networks.


# Resources

## eInk Display
https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT%2B

### Original example code in Python
It also explains dependencies from Debian. Useful to deal with PIL. Remember to port to Poetry.
https://github.com/waveshareteam/e-Paper/blob/master/RaspberryPi_JetsonNano/python/readme_rpi_EN.txt

### Manual
https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT_Manual#Demo_code

## Generic `python-sounddevice` library reference
https://python-sounddevice.readthedocs.io/en/0.5.1/usage.html

## Vosk Speech-to-Text recognition
https://alphacephei.com/vosk/install
https://alphacephei.com/vosk/models

## Google Gemini
https://ai.google.dev/gemini-api/docs/migrate
https://ai.google.dev/gemini-api/docs/rate-limits
https://aistudio.google.com/usage?timeRange=last-28-days&project=gen-lang-client-0547047381&tab=rate-limit

### Commands 
https://github.com/googleapis/python-genai#manually-declare-and-invoke-a-function-for-function-calling

### Chat history
https://stackoverflow.com/questions/78534769/how-to-include-chat-history-when-using-google-geminis-api

### Trivago MCP Server
https://mcp.trivago.com/docs

### FastMCP & Gemini
https://gofastmcp.com/integrations/gemini
https://github.com/stepanogil/mcp-sse-demo?tab=readme-ov-file

### Make Gemma3 to use native tools for Ollama
https://github.com/IllFil/gemma3-ollama-tools
https://www.philschmid.de/gemma-function-calling

## Geekworm X1203 UPS
Use the USB-C (5v/5A) from the UPS and not from the Raspberry Pi.
If connected without software, it will behave as follows:

- When connected it, the Raspberry Pi will start automatically
- The charging will start also automatically. One led blinks. There are 3 green leds that indicate the battery level.
- When shutting down the Raspberry Pi, it will remain on.
- To completelly shut it down, press the UPS power button 3 times.
- If a momentary button is connected to the XH2.54 dedicated socket, it also needs 3 times.
- To turn it on again, a single push to any of above buttons will do.

The software and some instructions can be found here:
https://wiki.geekworm.com/X1203
https://suptronics.com/Raspberrypi/Power_mgmt/x120x-v1.0_software.html

⚠️ Its control per software implies the use of `I2C`. At this point we should already have it
activated as the eInk and the LED matrix need it as well. Otherwise, read how to activate the
`I2C` feature through the `sudo raspi-config` command.

### Which I2C address is the UPS connected to?
To see which address the UPS is connected (docs says 0x36)
```
sudo i2cdetect -y 1
```

### How to update the RPi5 EEPROM so that all powers off together

In a terminal in the RPi, edit the EEPROM config:
```
sudo rpi-eeprom-config -e
```

Change the setting of `POWER_OFF_ON_HALT` from `0` to `1`,
Add `PSU_MAX_CURRENT=5000` at the end of the file that reads like this:
```
[all]
BOOT_UART=1
BOOT_ORDER=0xf14
POWER_OFF_ON_HALT=1
PSU_MAX_CURRENT=5000
```

Reboot

## Some newbie Debian docs for setting up stuff

### Make Pitxu to start at boot

https://www.thedigitalpictureframe.com/ultimate-guide-systemd-autostart-scripts-raspberry-pi/

See [The `pitxu.service` file in the /bin folder](./bin/pitxu.service)

1. Ensure that this file has `644` permissions
2. Create a soft link from `/etc/systemd/system/` to this file:
```
cd /etc/systemd/system/
sudo ln -s /home/xavier/pitxu/bin/pitxu.service pitxu.service
```

3. Reload the systemd daemon and enable the service
```
sudo systemctl daemon-reload
sudo systemctl enable pitxu
```

Further updates do not need to repeat point 3, but if the filename changes.

### Clear the displays on every shutdown and reboot

https://askubuntu.com/a/416330

See [The `k99_cleanup_pitxu` file in the /bin folder](./bin/k99_cleanup_pitxu)

1. Ensure that this file has `755` permissions
2. Create a soft link from `/etc/rc0.d/` to this file. This will clear the displays on reboot
```
cd /etc/rc0.d/
sudo ln -s /home/xavier/pitxu/bin/k99_cleanup_pitxu k99_cleanup_pitxu
```

3. Create a soft link from `/etc/rc6.d/` to this file. This will clear the displays on shutdown
```
cd /etc/rc6.d/
sudo ln -s /home/xavier/pitxu/bin/k99_cleanup_pitxu k99_cleanup_pitxu
```

### Make Debian `journalctl` to store persistent

⚠️ didn't work.

https://unix.stackexchange.com/a/414301

By default Debian's journal saves no files to disk. We need to change that so that we can see what happens during shutdown (if we want)

1. Edit `/etc/systemd/journald.conf`
2. Change the configuration so that the following parameters are uncommented and with the following values:
```
Storage=persistent      # This will persist the logs, even after reboot.
MaxRetentionSec=1week   # This will rotate the logs, cleaning them after a week
```

3. Add your user to the journal group
```
sudo usermod -a -G systemd-journal xavier
```

4. Restart the journal servie
```
systemctl restart systemd-journald
```

## Maybe replace Vosk by Whisper

https://github.com/FR33TR1ST/VoiceAssistant/blob/5e046b16a9ae32ba6e8aa5d595cffb9cbf221a6d/Voice_Asistant.py


# 😄 Fun fact

### The very first conversation with Pitxu was 2025-06-02 [commit hash: [fcaccfc](https://github.com/XaviArnaus/pitxu/commit/fcaccfc57b379cc9883646be57aca066c3d593d5)]

In Mac OS - catalan
- Dictation is good
- eInk is mocked
- Gemini improved very significantly after switching from single query (without context) to chat (with context)
- Speech is ok
- 🙂 Works pretty good

In RPi 02W - catalan
- Dictation takes ~4s
- eInk takes ~2s (still fullscan)
- Gemini takes ~1s (same as above)
- Speech is ok.
- 😕 Good quality but pretty slow all in all.