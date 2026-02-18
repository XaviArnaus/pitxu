# Specific CUSTOM overlay to allow PWM correct setup in Raspberry Pi 5

This is hunted from internet while trying to figure out how to get the Hardware PWM to work.

**Symptom was:**

The overlay `pwm-2chan` does not load, and therefore I can't use `rpi_hardware_pwm` package.

**Coming from:**

GPIO libraries (`gpiozero`, `lgpio`) behave with PWM as Software, not allowing to set up higher frequencies beyond ~10kHz.
We need to use the Hardware PWM, that the `rpi_hardware_pwm` allows. But this relies on an overlay `pwm-2chan` that I could not make to load during boot.

**Solution:**

Install a custom overlay that allows correct definition of the GPIO pins and the selection of the right PWM chip and channel.

**Points to take care:**

1. Raspberry Pi models 4 and below use the chip `pwmchip0`.
2. Raspberry Pi model 5 started using the chip `pwmchip2`.
3. From the Kernel 6.12.x, Raspberry Pi 5 moved to use `pwmchip0` again.

Be careful when reading resources in internet.

Also, other points:

4. With `rpi_hasrdware_pwm`, the instantiation of the device must be in a pretty low frequency, AND AFTERWARDS change the duty cycle to `0` and finally change the period (related to frequency) to the desired one. In my code:
```
# The initialisation needs to be at a pretty low frequency, otherwise we get "write error: Invalid argument".
pwm = HardwarePWM(pwm_channel=0, hz=100, chip=s0)

pwm.change_duty_cycle(0)
pwm.change_frequency(25_000)

pwm.start(initial_duty_cycle=0)
```

## Resources

I was trying to get to work the Python package `rpi_hardware_pwm`:
https://github.com/Pioreactor/rpi_hardware_pwm

I found this Github Gist:
https://gist.github.com/Gadgetoid/b92ad3db06ff8c264eef2abf0e09d569

How actually PWM works in Linkux
https://web.archive.org/web/20200722035349/https://jumpnowtek.com/rpi/Using-the-Raspberry-Pi-Hardware-PWM-timers.html

Troubleshoot PWM
https://raspberrypi.stackexchange.com/questions/148769/troubleshooting-pwm-via-sysfs

Very nice explanation about working with overlays in RPi5
https://www.reddit.com/r/raspberry_pi/comments/1ns0c5e/raspberry_pi_5_hardware_pwm_setup_servo_motor/

Very interesting explanation of a debugging and making to work PWM, even for the previous Kernel chip 2 verion
https://forums.raspberrypi.com/viewtopic.php?t=388352

The actual post that conculdes that from kernel `6.12.x` the chip comes bac to be number 0 and not number 2
https://forums.raspberrypi.com/viewtopic.php?t=389179

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

### Read the asignations of the PWM chips and channels over the GPIO pins:

```
pinctrl get | grep PWM
```

showing:
```
12: a0    pd | lo // GPIO12 = PWM0_CHAN0
13: a0    pd | lo // GPIO13 = PWM0_CHAN1
18: a3    pd | lo // GPIO18 = PWM0_CHAN2
19: a3    pd | lo // GPIO19 = PWM0_CHAN3
```

where `PWx_CHANy` is:
- `x`: chip number
- `y`: channel number

### List which chips do we have available

```
ll /sys/class/pwm
```

