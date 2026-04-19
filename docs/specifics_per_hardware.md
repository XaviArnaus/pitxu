# Particularities regarding hardware configuration

As I have a pair of Raspberry Pi 5, I try different hardware configurations and case styles, that require some different set ups.
With this doc I try to register them so it's easier to reinstall and to reach conclusions.
First versions os Pitxu are gone without too much logging. All these docs started after them. Still, I try to recap the first 2 versions.

## Pitxu 1

Worked ok, low power consumption, mostly due to being SD card based and not using a DSI screen.

- Raspberry Pi 5 8GB + Active cooler
- Storage: SD card 64 GB
- Screens:
    - e-ink 2.13"
    - LED 8x8 Matrix
- Soundcard: USB
- Microphone: external
- Speakers: external, passive
- UPS: Geekworm X1203
- No case fans.

## Pitxu 2

The intention was to make it way more portable, smaller. It all went around a PiSugar Whisplay HAT that includes a 1.69" LCD screen and a WM8960 soundcard with all included.

It produced the merge of displays management into "foreground / background interactions", what used to be the e-ink (foreground) and the LED matrix (background)

The microphone configuration was horrible: placed just above the CPU fan. I had to deactivate the microphone that was facing the fan, leaving it with only one, internal. It was inside a small carton box, the input transcription was mediocre.

The internal speaker is not enough, as usually the environment is too noisy to actually hear anything.

- Raspberry Pi 5 8GB + Active cooler
- Storage: SD card 64 GB
- Screen: 1.69" LCD screen
- Soundcard: GPIO / HAT WM8960
- Microphone: internal
- Speakers: internal
- UPS: Geekworm X1203
- No case fans.

## Pitxu 3

The intention was to settle the best setup possible, regardless of space, trying to improve the input voice, the output sound and the visual interaction.

The big 5" DSI screen produced an iteration on the command callbacks, improving visualization.
It included 2 PWM case fans, that improved ventilation but also adds power consumption and overall noise.
The storage was SSD USB3 based, making the setup fast. The 128GB SSD died eventually and was replaced by a 256GB NVME via PCIe port.

This "static base" configuration triggered the work on a super small Raspberry Pi Zero 2W client Push-to-talk version, connecting to Pitxu 3 through 3 endpoints that performed the actual STT, Chatbot processing and TTS back to the client.

The setup is pretty power hungry. It eventually had 2 batteries, but it did not improve too much as apparently the UPS has a 5000 mAh battery limitation. This point also brought some work on the power consumption readings, commands and PWM management.

- Raspberry Pi 5 8GB + Active cooler
- Storage: 128GB SSD USB3 -> 256GB M.2 NVME PCIe
- Screen: 5" DSI
- Soundcard: USB
- Microphone: external
- Speakers: external
- UPS: Geekworm X1203
- 2 PWM case fans

Particularities in configs:

- ALSA Microphone needs to be set as Mono
- ALSA Microphone control is "Mic"
- ALSA Speaker control is "Speaker"
- Microphone sample rate is "Whatever the Mic Soundcard gives", rather than 16 kHz.
- PWM Case fans setup:
    - fans:
        - name: rear
            - pin: 13
            - is_pwm: True
            - pwm_frequency: 25000
            - chip: 0
            - channel: 1
        - name: side
            - pin: 12
            - is_pwm: True
            - pwm_frequency: 25000
            - chip: 0
            - channel: 0
    - pwm_thresholds:
        - threshold_25: 55
        - threshold_50: 65
        - threshold_75: 80
    

## Peque (Pitxu client)

TBD

## Pitxu 4

The intention was to come back to something more portable and small, trying a HAT soundcard that allows external microphone, also trying to reduce the power consumption.

The screen got reduced to 4.3" DSI, and the soundcard is a Raspiaudio Ultra + v3 (WM8960 chip). The internal microphone and speakers are great, but I'm unable to make the external micrphone to work.

It produced the work regarding initial resampling (so that we can work internally with 16 kHz), input preprocessing (voice filtering) and VAD, intending to reduce the consumption by moving to a callback approach besides the neverending-loop.

- Raspberry Pi 5 8GB + Active cooler
- Storage: 128GB M.2 NVME PCIe
- Screen: 4.3" DSI
- Soundcard: USB
- Microphone: internal / external
- Speakers: external
- UPS: Geekworm X1203
- 1 PWM case fan

Particularities in configs:
- ALSA Microphone needs to be set as Stereo
- ALSA Microphone control is "Capture"
- ALSA Speaker control is "Speaker"
- Microphone sample rate is 16 kHz.