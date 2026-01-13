# Pitxu
Chatbot project over Raspberry Pi 5

# Installation

## 1. Install system depencencies

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

### Dependencies related to `pulseaudio`

For the amount of control that one can have over the system's audio, I also install (and therefore rely on) PulseAudio. It is the one then really applying the sound control and mute from within the Chatbot's Tool function call, and also several handy scripts in `bin/`

For Debian based linux distros:
```
sudo apt install pulseaudio
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
sudo apt install python3-dev libjpeg-dev zlib1g-dev libfreetype6-dev libffi-dev portaudio19-dev python3-pyaudio swig liblgpio-dev i2c-tools pulseaudio
```


## 2. Install Poetry

```
curl -sSL https://install.python-poetry.org | python3 -
```

Remember to add the `poetry` path into PATH, inside `.bashrc`:
```
export PATH="/home/user/.local/bin:$PATH"
```

## 3. Ininitalize the project

```
make init
```

## 4. Generate all the config files out of the `dist` example ones

```
for file in config/*.yaml.dist; do cp "$file" "${file%.dist}"; done
```

... and edit it at your wish

## 5. Create an environment variables file

```
nano .env
```

... and add there your Google Gemini key, that you got for free from https://aistudio.google.com/app/apikey like

```
API_KEY=abcdefghijkl
```

You can also add here the credentials for sending emails through a Gmail account. It is only used by the Gemini tool that sends emails.
You have to previously activate 2-step verification and add Pitxu as a new App Password, and then use this password instead of the account's one.
```
EMAIL_USERADDRESS=oscar.pitxu@domain.com
EMAIL_USERNAME=oscar.pitxu@domain.com
EMAIL_PASSWORD=patati patata
```

## 6. Setup Pitxu as a service of the system

See [The `pitxu.service` file in the /bin folder](./bin/pitxu.service)

1. Ensure that this file has `644` permissions
2. Create a soft link from `/etc/systemd/system/` to this file:
```
cd /etc/systemd/system/
sudo ln -s /home/user/pitxu/bin/pitxu.service pitxu.service
```

3. Reload the systemd daemon and enable the service
```
sudo systemctl daemon-reload
sudo systemctl enable pitxu
```

Further updates do not need to repeat point 3, but if the filename changes.

## 7. Add `pitxu` and the rest of `bin/` into `PATH`

Add the following line into your `.bashrc`:

```
export PATH="/home/user/pitxu/bin:$PATH"
```

# Troubleshooting

## The sound is just full of noise

https://bbs.archlinux.org/viewtopic.php?id=185736

Play with PulseAudio configuration. Reducing the block size helped me.

Edit the Pulse audio configuration
```
sudo nano /etc/pulse/daemon.conf
```

and the following values fixed my issue
```
default-fragments = 5
default-fragment-size-msec = 2
```



