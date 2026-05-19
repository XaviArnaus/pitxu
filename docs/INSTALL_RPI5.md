# Installation on a Raspoberry Pi 5 8GB

This document explains how to setup the Raspberry Pi from scratch to have the Pitxu chatbot up and running.

# Hardware scope

This document assumes the following hardware:

- Raspberry Pi 5 8GB
- A soundcard with microphone and speakers.
- A display

The related sections about soundcard and display contain some help regarding the setup and compatibility, but take it as tip. In most of the cases it's up to you to write a class that transforms PIL images to whatever the device needs (for the displays), and to ensure that the setup is up and ready to send and receive `sounddevice.[RawInput|Output]Stream`.

At a Operating System level, it is assumed a Raspberry Pi with an official 64bit distribution (Debian Trixie) installed from the Raspberry Pi Imager.

## 0. Raspberry Pi 5 preparation

This section is aimed to prepare the RPi from scratch. This is a bit out of scope, so will only enumerate (my) setup.

### Burn a micro-SD card or a SSD USB drive

Use Raspberry Pi Imager to burn the Raspberry Pi OS into the main storage support of your preference.
- Micro SD card works good.
- SSD USB3 disk works better.
- NVME M.2 PCIe Gen3

**Some suggestions:**
Within the Raspberry Pi Imager, make sure that you activate and configure the following options, they will make the initial start easier and faster:
- Activate the SSH access.
- Define a Wifi connection.

### Notes about using a SSD USB3 disk

If you chose to rely on a SSD USB3 disk, make sure that after the RPi Imager finishes you re-connect the disk to the burner computer, edit the device's `/boot/config.txt` and add the following line (I did it at the top of the file):
```
# Enable USB 5V 5A
usb_max_current_enable=1
```

Get an extended article on how to install a RPi5 based on a SSD USB disk here: [Spawning a Raspberry Pi 5 with Raspberry Pi OS in a SSD SATA III disk](https://xavier.arnaus.net/blog/spawning-a-raspberry-pi-5-with-raspberry-pi-os-in-a-ssd-sata-iii-disk)

### Notes about using a NVME PCIe Gen3

https://www.waveshare.com/wiki/PCIe_TO_M.2_Board_(E)#Booting_from_NVMe_SSD

TL;DR:

1. Start from an installation over the SD (or any previous support)
2. Edit the EEPROM so that it wants to boot from the NVME
```
sudo rpi-eeprom-config --edit 
```

3. Add the line
```
NVME_CONTROLLER=1
```

4. Change the value of the BOOT_ORDER from `BOOT_ORDER=0xf41` to:
```
BOOT_ORDER=0xf416
```

5. Shutdown
6. Remove the SD card
7. Boot the machine.

⚠️ While initially appeared to work very good (fast, reliable), and therefore I moved to NVME M.2 disks in both test hardwares, in the long term both gave problems, like lack of power, giving plenty of issues, freezing, hanging, and at the end, failing during a EEPROM update in one Raspberry that left it unusable. I've moved back to SD card in the RPi that still works. At this point in time, I do not recommend using a PCIe NVME M.2 disk.

### First start

Most of these steps are optional, and depend on what are the features that you want **Pitxu** to support. Soundcards, Displays, UPSs and so on usually need to have activated the SPI, I2C and xxx interfaces, and maybe to add some overlays or extra config in `/boot/firmware/config.txt`. I mention all here, and you simply jump whatever does not fit in your setup.

#### Ensure Network connectivity and access (optional)

Once we know what is the IP of the host (check your router, or use tools like `arpscan` to find it out).

1. Add your development SSH Key into the RPi host, to avoid having to type your password every time. More info [here](https://xavier.arnaus.net/blog/set-up-the-ssh-key-authentication-between-hosts)
2. Add the RPi host's SSH Key into GitHub SSH Keys if needed, to be able to clone the repo later on.
3. Add a new Wifi connection relating to your phone's hotspot, so that you can use Pitxu on the go. Use `nmtui` for it.

#### Update the system to the latest version

This is important as some of the hardware - software interconnections are quite edgy and improvements and bugfixes appear often.

```
sudo apt update
sudo apt full-upgrade
sudo rpi-eeprom-update -a
sudo reboot
```

#### Post-installation in `raspi-config`

We need to do some post installation setup through the RPi configuration tool:
```
sudo raspi-config
```

Skip whatever that does not fit to the hardware that you may have connected.

1. Activate the SPI interface under `3 Interface Options > I4 SPI`
2. Activate the I2C interface under `3 Interface Options > I5 I2C`
3. Configure the system Locale under `5 Localisation Options > L1 Locale`
4. Expand the filesystem with `6 Advanced Options > A1 Expand Filesystem`
5. Activate the 3rd Gen PCIe speed (for the AI HAT+2) at `6 Advanced Options > A8 PCIe Speed`

And reboot again.

### Update the RPi5 EEPROM so that all powers off together (optional)

This is useful for when we use a UPS that is able to self-power off on halt. It's also useful for a correct self-shutdown when triggering the Chatbot Tool to shutdown the system.
Tested with [Geekworm X1203 UPS](https://wiki.geekworm.com/X1203).

ℹ️ My UPS needs I2C as we did above. Refer to the specifications of your UPS.

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

Be careful with the parameters there that are not related to this section. For example, the lines above reflect my previous installation over a SD card, but the following ones reflect my installation on a SSD USB3 drive (note the `BOOT_ORDER` value):

```
[all]
BOOT_UART=1
POWER_OFF_ON_HALT=1
BOOT_ORDER=0xf461
PSU_MAX_CURRENT=5000
```

... and the following reflect my installation over NVME. Note the last line `NVME_CONTROLLER=1` and the different value on `BOOT_ORDER`

```
[all]
BOOT_UART=1
BOOT_ORDER=0xf416
POWER_OFF_ON_HALT=1
PSU_MAX_CURRENT=5000
NVME_CONTROLLER=1
```

### Set up your soundcard

The sound setup depends of you, but it's mandatory. In my current installation I'm using a USB Soundcard ant everything is setup already out of the box.
I also tried the following soundcards and I leave some references here. Refer to your soundcard details to properly install it and leave it ready.

Make sure that the system works through ALSA. Pitxu has Chatbot Tools to manage the audio that rely on `alsactl` shell commands.

In the `bin/` directory are shipped some tools to test the configuration. Take note which soundcard index and name you have as well as its device ID, and change the values in the commands as you need. The following commands will tell you this:
```
aplay -l
arecord -l
```

This page relate to this values later on.

#### Waveshare WM8960 Hi-Fi Sound Card HAT for Raspberry Pi, Stereo CODEC, Play/Record

- Integrated Mic, jack and screw connectors for speakers.
- Uses I2C, activated as explained above.
- https://www.waveshare.com/wiki/WM8960_Audio_HAT

#### RASPIAUDIO ULTRA+ V3
https://forum.raspiaudio.com/t/ultra-installation-guide/21
⚠️ I can't make it to work: Fully detected but no sound. Mic works, records a file and can hear in other computer. 
✅ Used the Optional method 2 (same as automatic, but adding the overlay in the `/boot/firmware/config.txt`)
❗️ Use `alsamixer` to rise up volumes and unmute channels!!! 

⚠️ External microphone does not work.


#### PiSugar Whisplay HAT

- Integrated Mic and Speaker. The left channel mic is placed in the bottom side of the board, so it faces directly the CPU fan. This dramatically reduces the quality of the input, making the whole Pitxu experience mediocre.
- Uses I2C, activated as explained above.
- https://github.com/PiSugar/whisplay

#### Generic USB Soundcard

- Pick your wish. Provides freedom for the actual Mic and Speaker through an "always-working" USB interface. Frees up GPIO connections but it's a mess of cables in a future enclosure.
- Tried successfully:
  - https://eu.ugreen.com/products/ugreen-usb-to-3-5mm-headphone-audio-adapter
  - https://sabrent.com/products/AU-MMSA

⚠️ Faced the issue that after several hours the microphone stops working, and therefore Pitxu does not wake up.
❓ Tried to disable the USB auto power saving:

1. Get the *Vendor ID*, the *Product ID* and the *Product* name of the USB sounbcard (for example, see line 4 here):
```
$ lsusb

Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
Bus 003 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
Bus 003 Device 002: ID 0d8c:0014 C-Media Electronics, Inc. Audio Adapter (Unitek Y-247A)
Bus 004 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
```

2. Confirm it with looking at the udev devices. First command shows the devices, second shows info about one (Bus-Device):
```
udevadm info -a --path /sys/bus/usb/devices/
udevadm info -a --path /sys/bus/usb/devices/3-2
```

3. Create an `udev` rule
```
sudo nano /etc/udev/rules.d/10-usb-audio.rules
```

4. Add the following 3 lines. Edit with your *Vendor ID*, *Product ID* and *Product* name:
```
ACTION=="add", SUBSYSTEM=="usb", ATTRS{idVendor}=="0d8c", ATTR{idProduct}=="0014", ATTR{product}=="USB Audio Device", TEST=="power/control", ATTR{power/control}:="on"
ACTION=="add", SUBSYSTEM=="usb", ATTRS{idVendor}=="0d8c", ATTR{idProduct}=="0014", ATTR{product}=="USB Audio Device", TEST=="power/autosuspend", ATTR{power/autosuspend}:="-1"
ACTION=="add", SUBSYSTEM=="usb", ATTRS{idVendor}=="0d8c", ATTR{idProduct}=="0014", ATTR{product}=="USB Audio Device", TEST=="power/autosuspend_delay_ms", ATTR{power/autosuspend_delay_ms}:="-1"
```

4. Reboot

### Setup your display

The display will use a defined interface. In my current installation I'm using a 5" DSI display and everything works out of the box. I've also tried the following soundcards and I leave some references here. Refer to your display details to properly install it and leave it ready.

Pitxu is designed as a 2-channel display interaction: One for foreground notifications (the main one) and one for background notifications (speaking and thinking animations, and status notifications). Pitxu is shipped with support for Foreground with a 2.13" e-Ink display and Background for a 8x8 Matrix LED. For a single display setup the Foreground is presented as an overlay over the Background animations, and has been tested in a 1.69" LCD and a 5" LCD. Other displays can be supported but the "driver" (the bytes of PIL images to the devices) has to be programmed by you (easy task with the provider examples).

⚙️ ToDo: Write a guide for creating "drivers" for displays.

#### Waveshare 2.13inch E-Paper HAT+

- Slow refresh but contained consumption.
- Uses SPI, activated as explained above.
- https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT+

#### 8x8 Matrix LED

- Very simple and old school appeal
- Based on chip Max7219. Uses SPI, activated as explained above.
- https://www.az-delivery.de/en/products/64er-led-matrix-display

#### PiSugar Whisplay HAT

- Regardles of the all-in-one packaging, it is a simple ST7789 (specifically a ST7789P3) which is common.
- Uses SPI, activated as explained above.
- https://github.com/PiSugar/whisplay

#### Waveshare 5 inch Touchscreen DSI LCD (C)

- Clear and fast. Touchscreen not yet used. Behaves as a main Linux display, and Pitxu interacts via it's framebuffer.
- Uses DSI interface, the RPi5 has 2. The provider recommends the one most far from the USB connections. The DSI interface Frees up GPIO connections. The Touchscreen is ignored ATM, maybe future features for Pitxu.
- https://www.waveshare.com/wiki/5inch_DSI_LCD_(C)

### Setup PWM case fans

Every PWM fan needs a 5v (red), ground (black) and TX/PWM (blue) cable. If your fan has 4 pins (RX/RPM yellow cable), just keep this unused.

1. Connect the red and black into free GPIO pins for power and ground, or to any power source (I have it connected to power connectors on the UPS).
2. Connect the blue cable into a PWM GPIO pin (GPIO 12 or 13)

Every fan needs a dedicated GPIO pin. 2 fans need 2 GPIO pins.
Every fan needs then a dedicated combination _device_ & _channel_. By default the RPi comes with one single device, and the normal CPU fan is connected to device 0 & channel 4.

See your available device and channel with:
```
sudo cat /sys/kernel/debug/pwm
```

You'll see an output like:
```
0: platform/1f0009c000.pwm, 4 PWM devices
 pwm-0   ((null)              ): period: 0 ns duty: 0 ns polarity: normal
 pwm-1   ((null)              ): period: 0 ns duty: 0 ns polarity: normal
 pwm-2   ((null)              ): period: 0 ns duty: 0 ns polarity: normal
 pwm-3   (cooling_fan         ): requested enabled period: 41566 ns duty: 20375 ns polarity: inverse usage_power
```

Also, keep in mind that if you use a GPIO soundcard, it needs a PWM channel for itself. On my tests, just by doing this above it wouldn't work. I've added the PWM overlay and defined which pin I want to use. For that:

3. Edit the RPi config file
```
sudo nano /boot/firmware/config.txt
```

4. Add the following line AT THE TOP OF THE FILE:
```
dtoverlay=pwm,pin=13,func=4
```

5. Reboot.

After that, the command above gave the following output:
```
sudo cat /sys/kernel/debug/pwm

0: platform/1f00098000.pwm, 4 PWM devices
 pwm-0   ((null)              ): period: 0 ns duty: 0 ns polarity: normal
 pwm-1   (sysfs               ): requested enabled period: 40000 ns duty: 10000 ns polarity: normal
 pwm-2   ((null)              ): period: 0 ns duty: 0 ns polarity: normal
 pwm-3   ((null)              ): period: 0 ns duty: 0 ns polarity: normal

1: platform/1f0009c000.pwm, 4 PWM devices
 pwm-0   ((null)              ): period: 0 ns duty: 0 ns polarity: normal
 pwm-1   ((null)              ): period: 0 ns duty: 0 ns polarity: normal
 pwm-2   ((null)              ): period: 0 ns duty: 0 ns polarity: normal
 pwm-3   (cooling_fan         ): requested enabled period: 41566 ns duty: 12225 ns polarity: inverse usage_power
```

ℹ️ Note that this output comes AFTER having Pitxu up and running, so the app requests the fan speed and that is then managed by the system as shown.

#### Issues with a USB soundcard and 2 fans

On my tests with a USB card and 2 case fans I encountered that I could not use the 2 channels PWM overlay as it should:
```
dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4
```

With some research, I found a side solution that I explain here: [RPi5 PWM overlay](../overlays/pwm/README.md)
Keep in mind that this solution does not work well with a GPIO soundcard (for example a _WM8960_): the soundcard is not detected.


## 1. Install system depencencies

Here we setup the application and its dependencies. These can be also at Linux level to support the interaction with the hardware. Most of the times it comes dictates by the code approach and which libraries it uses, so if you feel more confortable with other backend, go to the code and make it happen, and send me a Pull Request to include the support!

### Initial Linux basic setup

The following is initially required:

#### Install Git

```
sudo apt install git
```

### Debian packages to support the Python application

The following are the system dependencies that are needed at OS level so that the Python application works.

#### ❗️ All Linux/Debian code dependencies in one line

Debian packages can be installed all at once. Just make sure that I did not forget to add in this line anything from the below sections, I'm just putting them all together here.

```
sudo apt install python3-dev libjpeg-dev zlib1g-dev libfreetype6-dev libffi-dev portaudio19-dev python3-pyaudio swig liblgpio-dev i2c-tools libasound2-plugins dkms hailo-h10-all
```

#### Ability to build other dependencies: `python3-dev`

Some dependencies are built at installing time. Please have the `python3-dev` pachage installed beforehand:

```
sudo apt install python3-dev
```

#### Related to `Pillow`

This is needed for the internal Pillow support, we interact with the displays by drawing images.

```
sudo apt install libjpeg-dev zlib1g-dev libfreetype6-dev
```

#### Related to `Gemini`

This is needed for the internal Gemini support.

```
sudo apt install libffi-dev
```

#### Related to `pyaudio`

This is needed for the internal Pyaudio support, required by the `sounddevices` package.

```
sudo apt install portaudio19-dev python3-pyaudio
```

ALSA needs a plugins package to allow samplerate conversions.

```
sudo apt install libasound2-plugins
```

#### Related to `lgpio`

This is needed for the internal GPIO support

```
sudo apt install swig liblgpio-dev
```

#### Related to `i2c`

This is not needed for the Python / Poetry application to work, but it's useful to debug and identify the own hardware.

```
sudo apt install i2c-tools
```

#### Related to `whisper`

This is needed for the Whisper Speech-To-Text transcription

⚠️ I'm not really sure that it is needed, as we're not doing any conversion or picking up audio files. I just followed the instructions but I doubt that it is needed.

```
sudo apt install ffmpeg
```

#### Related to `AI Hat+ 2`

These packages are needed for the use of the AI Hat+ 2 accelerator.

```
sudo apt install dkms hailo-h10-all
```

### Packages to support some other operations

The packages suggested to install here are optional, but they are referenced by some funcionality and are strongly encouraged

#### `jq` to process JSON at shell.

This is used for presenting the pitxu server answers when being triggered from the `bin/pitxu` script

```
sudo apt install jq
```

### Add the user into the `video` group (only required for the DSI display)

By using the DSI display, the _driver_ writes directly to the system's **framebuffer**. Framebuffers are controlled by `root`. You can run the script with `sudo`, but you also can add your user into the `video` group so it gains group privileges. 
```
sudo usermod -a -G video user
```

... where `user` is your user.

To know if the user was added correctly, log out and log in again from your ssh session after adding the user into the group, and then run:
```
groups
```

This will tell you in which groups the your user is registered.

⚠️ Tracing the execution as shipped by the Pitxu repo, the `systemd` service (ran by `user`) executes `bin/pitxu`, which at its time runs `poetry run main`. This means that the actual execution of Pitxu is done by `user`. Therefore, we need `user` to be part of `video`.  

References:
- https://gist.github.com/Quasimondo/e47a5be0c2fa9a3ef80c433e3ee2aead
- https://medium.com/@avik.das/writing-gui-applications-on-the-raspberry-pi-without-a-desktop-environment-8f8f840d9867

### Raspberry Pi 5 AI Hat+ 2

I've installed a [Raspberry Pi 5 AI Hat+ 2](https://www.raspberrypi.com/documentation/accessories/ai-hat-plus.html).
It is a PCIe device. If you're using a PCIe disk, think about a multiplexer or challenge yourself if you really can't live with a SD card. The installation instructions here are assuming that the PCIe port is free.

⚠️ Keep in mind that this is only meant to be executed in a Raspberry Pi. A development computer (like a MacOS) is not mocked for it and should not even be tried.

Once the packages are installed and the machine, we need to reboot again
```
sudo reboot
```

#### System installation

Now, we run the following command to ensure that we have the device ready:
```
hailortcli fw-control identify
```

... which has to return an output similar to:
```
Executing on device: 0001:01:00.0
Identifying board
Control Protocol Version: 2
Firmware Version: 5.1.1 (release,app)
Logger Version: 0
Device Architecture: HAILO10H
```

If we don't receive any output, most likely the device is not recognized. We can ensure this by running:
```
hailortcli scan
```

if the output is `Hailo devices not found`, it is then clear that we have any hardware issue. Double check the PCIe connections, most likely the PCIe cable is in the other way around (on the RPi, the brown side looks outside the card, and in the HAT, the open (copper) connections are up)

#### Software layer installation

Even the docs indicate to install the Software layer and the Web UI, the second won't be needed. Focusing in the Software layer, which is basically starting the `hailo-ollama` service that will respond to the POST HTTP requests.

⚠️ The Pitxu application is a Python app that has its own SDK. This means that actually the following commands are not needed because the whole server / client and model handling are done by the app itself. Still, to be able to test the AI Hat is good to have it installed because once we close the server running in the terminal, the whole instance is teared down freeing memory.

1. Download the `hailo-ollama` package. At the moment of writing, it's the version 5.1.1 according to [the documentation](https://www.raspberrypi.com/documentation/computers/ai.html#step1-llm):
```
wget https://dev-public.hailo.ai/2025_12/Hailo10/hailo_gen_ai_model_zoo_5.1.1_arm64.deb
```

2. Install the `hailo-ollama` package:
```
sudo dpkg -i hailo_gen_ai_model_zoo_5.1.1_arm64.deb
```

3. Run the `hailo-ollama` server:
```
hailo-ollama
```

This will kidnap the terminal session, as the server is not running as a system service. The next commands need to be running in a **separate terminal session, without closing this one**.

4. List the available models:
```
curl --silent http://localhost:8000/hailo/v1/list
```

5. Download the desired model, for example for `qwen2.5-instruct:1.5b`:
```
curl --silent http://localhost:8000/api/pull \
     -H 'Content-Type: application/json' \
     -d '{ "model": "qwen2.5-instruct:1.5b", "stream" : false }'
```

This model is around 3.3GB at the moment of writing, so it can take a while to download.

6. Test the communication with the model, sending any Chat query to it:
```
curl --silent http://localhost:8000/api/chat \
     -H 'Content-Type: application/json' \
     -d '{"model": "qwen2.5-instruct:1.5b", "messages": [
        {"role": "system", "content": "You are a concise assistant. Answer just what is asked, no further explanations"},
        {"role": "user", "content": "What is 2 + 3?"}
      ]}'
```

## 2. Clone the repository

Taking `/home/user/` as a target for the project.

```
git clone git@github.com:XaviArnaus/pitxu.git
```

## 3. Configure ALSA to the Pitxu parameters

### Add the `bin/` directory into the system's path

This way all Pitxu binaries can be executed easily.
Add the following line at the end of your `~/.bashrc` file:
```
export PATH="/home/user/pitxu/bin:$PATH"
```

Save, exit, and reload the session:
```
source ~/.bashrc
```

### ALSA related configuration files

Some system setup is needed that require configuration files. The repo contains a working configuration for ALSA, Pitxu as a Systemd service, and final cleanu-up scripts. They are meant to be linked into the Debian expected destinations. The `bin/pitxu` binary can place the links automatically with:
```
pitxu link_alsa
```

It goes one by one, showing what file it wants to link to (in case that you already have one, be aware), and offers the option to cancel.
Take a look at the content of the files that it will link. There is hardware configuration that may not relate to your device. In particular, the Index/Name of your card and the Device ID in the following files:

- ALSA config file [config/system/asound.conf](./config/system/asound.conf)
- ALSA Card index [config/system/sound.conf](./config/system/sound.conf)

## 4. Install Poetry

```
curl -sSL https://install.python-poetry.org | python3 -
```

Remember to add the `poetry` path into PATH, inside `.bashrc`:
```
export PATH="/home/user/.local/bin:$PATH"
```

## 5. Ininitalize the project

This creates the Python Virtual Environment and installs / builds all the Python packages required by the application.

```
make init
```

If it complains about the `python.lock`, use `make update` instead.


## 6. Generate all the config files out of the `dist` example ones

```
for file in config/*.yaml.dist; do cp "$file" "${file%.dist}"; done
```

... and edit it at your wish

## 7. Create an environment variables file

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

## 8. Preliminary test

At this point, Pitxu should be prepared to run. The configuration changes that we did require that we reboot:
```
sudo reboot
```

After that, we should be up and running with the ALSA configuration. I recommend to run the following test: [bin/test_record_and_play_alsa.sh](./bin/test_record_and_play_alsa.sh)

Now, we can test Pitxu as is in the current SSH terminal. The RPi should become Pitxu 100% working. Just run Pitxu's binary without parameters:
```
pitxu
```

## 9. Setup Pitxu as a service of the system

Adding Pitxu as a service allows the RPi to automatically start Pixtu on start by itself.
Use the Pitxu binary to create the necessary links from the Pitxu service definition to the actual Systemd services location.
It will also place links for the shutdown and reboot that clean properly the system when closing it.
```
pitxu link_service
```
