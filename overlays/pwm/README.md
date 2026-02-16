# Specific CUSTOM overlay to allow PWM correct setup in Raspberry Pi 5

This is hunted from internet while trying to figure out how to get the Hardware PWM to work.
Symptom was: the overlay `pwm-2chan` does not load, and therefore I can't use `rpi_hardware_pwm` package.

## Resources

I was trying to get to work the Python package `rpi_hardware_pwm`:
https://github.com/Pioreactor/rpi_hardware_pwm

I found this Github Gist:
https://gist.github.com/Gadgetoid/b92ad3db06ff8c264eef2abf0e09d569

## How to make it work

### 1. Compile the file

```
dtc -I dts -O dtb -o pwm-pi5.dtbo pwm-pi5-overlay.dts
```

### 2. Install

```
sudo cp pwm-pi5.dtbo /boot/firmware/overlays/
```

### 3. Add the overlay into the `/boot/firmware/config.txt`

```
dtoverlay=pwm-pi5
```

### 4. Reboot

## How to use it

