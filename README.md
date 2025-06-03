# pitxu
Chatbot project over Raspberry Pi Zero 2w


# Install

This project works with a bunch of system resources. This means that for Python to be able to
compile the dependecies we need to have some packages in the OS level.

⚠️ Due to the Text-to-Speech (at least), the linux system must be 64 bits. This is choosen when burning the new Raspberry Pi OS image using the official Imager. Make sure that you choose a 64bit distro.

## Linux (Raspberry Pi)

### Dependency in general to build other dependencies: `python3-dev`

Some dependencies ar built at installing time. Please have the `python3-dev` pachage installed beforehand:

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

### ❗️ All Linux/Debian dependencies in one line
Just make sure that I did not forget to add here anything from above. Just put the all together.

```
sudo apt install python3-dev libjpeg-dev zlib1g-dev libfreetype6-dev libffi-dev portaudio19-dev python3-pyaudio
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

## Ininitalize the project

```
make init
```

## Notes regarding the Python dependencies installation

In lot of cases, poetry builds the dependencies and they fail due to diverse issues.

### Numpy
Numpy is a dependency from Piper. It is also mentioned in one of the Vosk (STT) examples as a tool for calculation.
I have it as a direct dependency as it gave some headaches. At the end, it gets installed but needs **VERY MUCH TIME**.
It's installation (isolated back then with `poetry add numpy -vvv`) was monitored with another ssh window running `htop`,
And it only worked after a reboot and directly install it.

### piper-phonemize
piper-phonemize is a dependency from Piper. It has well documented issues due to the lack of wheels to a big chunk of
architectures & python versions. The most suggested fix is to build the package matching your version and architecture needs
but on Feb 2025 appeared a fix in PyPi from someone that forked and generated installable builds,and also fixing packaging to be able to build on demand.
My approach has been to add it as a first level dependency and then install `piper-tts`, which should find the dependency and respect it.
Source: https://github.com/rhasspy/piper/issues/509
It didn't really work like that. They both need to be installed through the `python shell`'s `pip3 install`, as seen below.

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

... and then you can continue as usual:

```
poetry shell
pip3 install gpiozero
pip3 install piper-phonemize-fix 
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

# Resources

## eInk Display

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
