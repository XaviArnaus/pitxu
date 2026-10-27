# Issue: Input sound capture stops sending chunks after some hours

While having the application up and running, I identified an issue that effectively stops the aplication to be responsive:

After some time of running, the CaptureHandle callback stops receiving input audio chunks. Therefore, no transcription nor speech
recognition is performed.

It is a very annoying issue because one can't simply debug it, it's just a matter of having the app open and try to catch when it happen and what was the current context to try to identify what can be toe origin.

## First ideas and tests: Power Saving

The first idea was Power Saving, like the USB device goes to sleep after some time of being unused, and then never comes back.
I've tried the following actions to control the Power Saving:

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

⚠️ It did not really worked. Trying the next:

5. Add a new modprobe rule:
```
sudo nano /etc/modprobe.d/audio_disable_powersave.conf
```

and add this content:
```
options snd_usb_audio power_save=0
```

⚠️ Also didn't work. Power saving appears to be correctly identified but the issue stays.

## Second: Improve Processing and Error handling in the Capture Handler's callback itself.

The Sounddevice's RawInput calls a defined callback passing an audio chunk for me to use it.

Turns out that if there is a crash / Exception in the callback, it silently dies and stops sending chunks.
It also may happen if the processing of the chunk takes too much time, and apparently the Sounddevice's call to the callback
eventually stops sending chunks.

I did 2 main things to try to cover this situation:

### 1. Move out everything done inside the callback

I was doing a bunch of preparation work inside that initial callback:

1. Conversion of the input audio samplerate, from whatever comes to 16K (if needed)
2. Adding the timestamp to the chunks, if the option is active
3. Adding the silent chunks to the silent queue, if the option is active

Turned out that this is too much for a "quick" callback, so I moved everything out into a threaded process. The callback now only feeds an internal queue and this gets processed by that threaded process, in a try to disconnect the direct work that the callback needs to do

### 2. Implement Error handling inside the callback

According to some research, Sounddevice, that uses the PortAudio backend behind the scenes, can stop delivering chunks if any exception bubbles up to it inside the callback, so I covered all work there with a try/except and try to add some debugging messages there.

### Result

The behaviour improved a lot, having the application way more time up and running, but still faced several `input overrun" and after some time the chunks stopped comming.

## Third: Ensure 16KHz audio input samplerate

Even I had the samplerate conversion outside the callback, felt like the extra work of samplerate conversion done by the app was occupying the CPU too much, that Sounddevice maybe:

- Feeded the queue faster than the queue was being processed
- Felt a lack of resources

which brought it to stop sending chunks.

I worked out the ALSA driver so that it performs the samplerate conversion behind the scenes, so when the application reads the input audio, it is done directly at 16 KHz, so we don't need any conversion in the app.

This effectively boosted the time that the application keeps working, and the chunks are getting sent continuously.

### Add a specific configuration to the ALSA infra

We need to have an ALSA configuration file that creates a virtual device that gets the samplerate covnerted automatically. See [this configuration file](../config/system/asound.conf).

Then copy or link this file into the `/etc/.` directory.

### Tell the system to use the `plug` plugins

There is an environment variable that needs to be activated so that the ALSA subsystem uses the `plug` plugins.

For that, add the following line to the `.env` file in the application (needs to be there, because Pitxu is used as a system service, so exporting the environment var in your `.bashrc` would not work)

```
PA_ALSA_PLUGHW=1
```

And now it's the time to restart the system. If you have Pitxu already set as a system service, ssh into the system after rebooting and stop it.

### Make the application to use this virtual device

Identify which is the device number that uses the new configuration that we set up for ALSA:

```
make sounddevices
```

This should give an output similar to the following:

```
   0 USB Audio Device: - (hw:0,0), ALSA (1 in, 2 out)
   1 sysdefault, ALSA (128 in, 128 out)
   2 front, ALSA (0 in, 2 out)
   3 surround40, ALSA (0 in, 2 out)
   4 iec958, ALSA (0 in, 2 out)
   5 spdif, ALSA (1 in, 2 out)
   6 lavrate, ALSA (128 in, 128 out)
   7 samplerate, ALSA (128 in, 128 out)
   8 speexrate, ALSA (128 in, 128 out)
   9 a52, ALSA (0 in, 6 out)
  10 speex, ALSA (1 in, 1 out)
  11 upmix, ALSA (8 in, 8 out)
  12 vdownmix, ALSA (6 in, 6 out)
  13 playback, ALSA (0 in, 128 out)
  14 capture, ALSA (128 in, 0 out)
  15 dmixed, ALSA (0 in, 2 out)
  16 array, ALSA (1 in, 0 out)
  17 dmix, ALSA (0 in, 2 out)
* 18 default, ALSA (128 in, 128 out)
```

The configuration file calls it `array`, here it is the number `16` for Input, which is what we want.
Then edit the `config/speech.yaml` pitxu configuration file and set the `input_device` to use the `16`.

Now (re)start the Pitxu application, and observe the logs saying that the input samplerate is now 16 kHz.




