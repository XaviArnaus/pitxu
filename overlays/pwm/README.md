# Specific CUSTOM overlay to allow PWM correct setup in Raspberry Pi 5

This is hunted from internet while trying to figure out how to get the Hardware PWM to work.
Symptom was: the overlay `pwm-2chan` does not load, and therefore I can't use `rpi_hardware_pwm` package.

## Resources

I was trying to get to work the Python package `rpi_hardware_pwm`:
https://github.com/Pioreactor/rpi_hardware_pwm

I found this Github Gist:
https://gist.github.com/Gadgetoid/b92ad3db06ff8c264eef2abf0e09d569

How actually PWM works in Linkux
https://web.archive.org/web/20200722035349/https://jumpnowtek.com/rpi/Using-the-Raspberry-Pi-Hardware-PWM-timers.html

Troubleshoot PWM
https://raspberrypi.stackexchange.com/questions/148769/troubleshooting-pwm-via-sysfs

## How to make it work

### 1. Compile the file

Please not that I already did and shipped the outcome in this same directory.
I compiled it the 2026-02-12 with the latest official Raspberry Pi OS.
Maybe you want to delete it first so that compiling does not fail to you.

```
dtc -I dts -O dtb -o pwm-pi5.dtbo pwm-pi5-overlay.dts
```

### 2. Install

```
sudo cp pwm-pi5.dtbo /boot/firmware/overlays/
```

### 3. Add the overlay into the `/boot/firmware/config.txt`

At the beggining of the file.
```
dtoverlay=pwm-pi5
```

### 4. Reboot

## Configuration on the `rpi_hardware_pwm` package:

It ends up as:
```
GPIO12 => chip 0, channel 0

GPIO13 => chip 0, channel 1

GPIO18 => chip 0, channel 2

GPIO19 => chip 0, channel 3
```

## Tools

### Check that the overlay was loaded:

```
sudo dtoverlay -r pwm-pi5
```

### Manually start the overlay

```
sudo dtoverlay pwm-pi5
```

### Show PWM devices

```
cat /sys/kernel/debug/pwm
```

### Debug overlays

Add `dtdebug=1` at the beginning of the `/boot/firmware/config.txt`
You van see the messages logged by
```
sudo vclog -m
```

