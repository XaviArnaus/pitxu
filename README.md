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

### ❗️ All Linux/Debian dependencies in one line
Just make sure that I did not forget to add here anything from above. Just put them all together.

```
sudo apt install python3-dev libjpeg-dev zlib1g-dev libfreetype6-dev libffi-dev portaudio19-dev python3-pyaudio swig liblgpio-dev
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

### Led Matrix
- Works good as a test in the main thread, I can't make it work properly in a subprocess:
    - Initialisation presents random (always the same) led on.
    - Flush to the device does not seem to work (it works when all is in the main thread, check test)
    - Only got to get flasshing random leds and bars.


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

### Commands 
https://github.com/googleapis/python-genai#manually-declare-and-invoke-a-function-for-function-calling

### Chat history
https://stackoverflow.com/questions/78534769/how-to-include-chat-history-when-using-google-geminis-api

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