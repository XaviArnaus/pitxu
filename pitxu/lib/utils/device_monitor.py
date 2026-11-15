import math
import platform
import threading
import time

from pyxavi import Config, Dictionary

from definitions import SHARED_MIC_VOLUME, SHARED_SPEAKER_VOLUME, SHARED_BATTERY_LEVEL, \
                        SHARED_SPEAKER_MUTED, SHARED_POWER_CABLE_CONNECTED, \
                        SHARED_CPU_TEMPERATURE, SHARED_CPU_FAN_RPM, \
                        SHARED_CASE_FAN_1_SPEED, SHARED_CASE_FAN_2_SPEED
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.hardware import AlsaMixer, PowerReader, ThermalReader


class DeviceMonitor(PyXavi):
    """
    The one place that gathers the readings of the device: volumes, battery, power cable,
    CPU temperature, CPU fan and case fans.

    - It is the ONLY code that talks to the hardware (through the readers of `lib/hardware`).
    - It is the ONLY writer of those shared memory values, so the displays (and anything else)
      can read them from the shared memory without asking.
    - The chatbot commands use its get_*() and set_*() functions. A get is always a live read,
      and every read or write also publishes the new value.

    tick() is meant to be called every second:
        - The power cable is read on every tick (a cheap GPIO read).
        - The case fans' speed (kept in memory by FanControl) is published on every tick.
        - The CPU temperature and fan are read every THERMAL_EVERY_SECONDS (two small sysfs reads).
        - The volumes and the battery are read at the beginning and then every LEVELS_EVERY_SECONDS.
          They need shell calls (amixer) or I2C, so they run in a short daemon thread that never blocks the caller.

    In the shared memory everything is a number. -1 means unknown. Booleans are 1 / 0.
    Everything else (the get_*() functions) returns None when unknown.

    Params:
        shared_memory: SharedMemoryManager to publish to. Optional: without it, nothing is published.
        fan_control: FanControl that holds the case fans status. Optional.
    """

    LEVELS_EVERY_SECONDS: int = 60
    THERMAL_EVERY_SECONDS: int = 5
    UNKNOWN: int = -1

    # The GPIO pin where the X1203 UPS reports the power loss detection (low = external power lost).
    PLD_PIN: int = 6

    # Values shown when the hardware is mocked (on the Mac).
    MOCKED_BATTERY_LEVEL: int = 50
    MOCKED_BATTERY_VOLTAGE: float = 4.0
    MOCKED_POWER_CONSUMPTION_WATTS: float = 10.0

    BATTERY_READ_RETRIES: int = 2

    # Shared memory slots for the case fans, following the order of `gpio.fans.devices`.
    CASE_FAN_INDEXES: list[int] = [SHARED_CASE_FAN_1_SPEED, SHARED_CASE_FAN_2_SPEED]

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(DeviceMonitor, self).init_pyxavi(config=config, params=params)

        self._shared_memory = self._xparams.get("shared_memory", None)
        self._fan_control = self._xparams.get("fan_control", None)

        self._is_linux: bool = platform.system() == "Linux"

        # UPS
        self._ups_is_mocked: bool = bool(self._xconfig.get("ups.mock", True))
        self._ups_i2c_address: int = int(self._xconfig.get("ups.i2c_address", PowerReader.GAUGE_ADDRESS))
        # How to detect the power cable: "gpio" reads the UPS pin, "disabled" always reports unknown.
        self._power_cable_detection: str = str(self._xconfig.get("ups.power_cable_detection", "gpio")).lower()
        if self._power_cable_detection not in ("gpio", "disabled"):
            self._xlog.warning(f"Unknown ups.power_cable_detection [{self._power_cable_detection}], using 'gpio'.")
            self._power_cable_detection = "gpio"
        self._pld_button = None

        # ALSA
        self._speaker_control: str = self._xconfig.get("text-to-speech.alsa_speaker_control_name", "Speaker")
        self._mic_control: str = self._xconfig.get("text-to-speech.alsa_mic_control_name", "Mic")
        self._mic_channel: str = "Mono" if self._xconfig.get("text-to-speech.alsa_is_mic_mono", True) else "Left"
        self._speaker_volume_addition: int = int(self._xconfig.get("text-to-speech.add_to_output_volume", 0))
        self._initial_mic_volume: int = int(self._xconfig.get("text-to-speech.alsa_initial_mic_volume", 60))

        # Everything that touches the hardware goes through this lock: the tick, its thread and the chatbot tools.
        self._lock = threading.RLock()
        self._published: dict[int, float] = {}
        self._warned_about_extra_fans: bool = False
        self._last_levels_sampled_at: float | None = None
        self._last_thermal_sampled_at: float | None = None
        self._levels_thread: threading.Thread | None = None

        # We want the microphone volume at a known level since the very beginning.
        if self._is_linux:
            self.set_mic_volume(self._initial_mic_volume)

    # ---- Periodic sampling ----

    def tick(self):
        """
        To be called every second.
        """
        try:
            self._sample_power_cable()
            self._sample_fans()

            if self._last_thermal_sampled_at is None or \
                    (time.monotonic() - self._last_thermal_sampled_at) >= self.THERMAL_EVERY_SECONDS:
                self._last_thermal_sampled_at = time.monotonic()
                self.get_cpu_temperature()
                self.get_cpu_fan_rpm()

            levels_are_due = self._last_levels_sampled_at is None or \
                (time.monotonic() - self._last_levels_sampled_at) >= self.LEVELS_EVERY_SECONDS
            levels_are_running = self._levels_thread is not None and self._levels_thread.is_alive()

            if levels_are_due and not levels_are_running:
                self._last_levels_sampled_at = time.monotonic()
                self._levels_thread = threading.Thread(target=self._sample_levels, name="DeviceMonitorLevels", daemon=True)
                self._levels_thread.start()
        except Exception as e:
            self._xlog.warning(f"DeviceMonitor tick failed: {e}")

    def _sample_power_cable(self):
        self.is_power_cable_connected()

    def _sample_fans(self):
        self.get_case_fans()

    def _sample_levels(self):
        try:
            self.get_mic_volume()
            self.get_speaker_volume()
            self.get_speaker_muted()
            self.get_battery_level()
        except Exception as e:
            self._xlog.warning(f"DeviceMonitor could not sample the levels: {e}")

    # ---- Volumes (ALSA) ----

    def get_mic_volume(self) -> int | None:
        if not self._is_linux:
            return None
        with self._lock:
            volume = AlsaMixer.get_volume(self._mic_control, self._mic_channel)
            self._publish(SHARED_MIC_VOLUME, volume)
            return volume

    def set_mic_volume(self, volume: int) -> int | None:
        if not self._is_linux:
            return None
        with self._lock:
            AlsaMixer.set_volume(self._mic_control, max(0, min(100, int(volume))))
            return self.get_mic_volume()

    def get_mic_muted(self) -> bool | None:
        """
        The ALSA mute of the microphone. Not the `microphone muted` flag, which is the app level mute.
        """
        if not self._is_linux:
            return None
        with self._lock:
            return AlsaMixer.get_mute(self._mic_control, self._mic_channel)

    def set_mic_muted(self, mute: bool) -> bool | None:
        if not self._is_linux:
            return None
        with self._lock:
            AlsaMixer.set_mute(self._mic_control, mute)
            return self.get_mic_muted()

    def get_speaker_volume(self) -> int | None:
        if not self._is_linux:
            return None
        with self._lock:
            raw = AlsaMixer.get_volume(self._speaker_control, "Left")
            volume = None if raw is None else max(0, raw - self._speaker_volume_addition)
            self._publish(SHARED_SPEAKER_VOLUME, volume)
            return volume

    def set_speaker_volume(self, volume: int) -> int | None:
        if not self._is_linux:
            return None
        with self._lock:
            volume = max(0, min(100, int(volume)))
            # Unless we want it at 0, we add the addition, to avoid being too low.
            raw = volume + self._speaker_volume_addition if volume != 0 else 0
            AlsaMixer.set_volume(self._speaker_control, min(100, raw))
            return self.get_speaker_volume()

    def get_speaker_muted(self) -> bool | None:
        """
        None when this soundcard has no mute switch (like the WM8960 Speaker), which is NOT the same as muted.
        """
        if not self._is_linux:
            return None
        with self._lock:
            muted = AlsaMixer.get_mute(self._speaker_control, "Left")
            self._publish(SHARED_SPEAKER_MUTED, None if muted is None else 1 if muted else 0)
            return muted

    def set_speaker_muted(self, mute: bool) -> bool | None:
        if not self._is_linux:
            return None
        with self._lock:
            AlsaMixer.set_mute(self._speaker_control, mute)
            return self.get_speaker_muted()

    # ---- Power (UPS and PMIC) ----

    def get_battery_voltage_and_capacity(self) -> tuple[float, float] | None:
        """
        (cell voltage in V, capacity in %), or None if unknown.
        """
        if self._ups_is_mocked:
            return self.MOCKED_BATTERY_VOLTAGE, float(self.MOCKED_BATTERY_LEVEL)
        with self._lock:
            for attempt in range(1, self.BATTERY_READ_RETRIES + 1):
                reading = PowerReader.battery_voltage_and_capacity(address=self._ups_i2c_address)
                if reading is not None:
                    return reading
                self._xlog.warning(f"⚠️ Retry {attempt}/{self.BATTERY_READ_RETRIES} reading the UPS battery level.")
            return None

    def get_battery_level(self) -> int | None:
        reading = self.get_battery_voltage_and_capacity()
        level = None if reading is None else math.ceil(reading[1])
        self._publish(SHARED_BATTERY_LEVEL, level)
        if reading is not None:
            self._log_debug(f"🔋 Current UPS battery level: {level} % (Voltage: {reading[0]:.2f} V)")
        return level

    def is_power_cable_connected(self) -> bool | None:
        """
        None when it can't be known: detection disabled, or the pin can't be read.
        """
        connected = self._read_power_cable()
        self._publish(SHARED_POWER_CABLE_CONNECTED, None if connected is None else 1 if connected else 0)
        return connected

    def _read_power_cable(self) -> bool | None:
        if self._power_cable_detection == "disabled":
            # Not trustworthy (or not wanted): report it as unknown, so nothing claims anything.
            return None
        if self._ups_is_mocked:
            return True
        with self._lock:
            try:
                if self._pld_button is None:
                    # Claimed only when we really use it, and only once.
                    from gpiozero import Button
                    self._pld_button = Button(self.PLD_PIN)  # down = power lost, up = power ok
                return not self._pld_button.is_pressed
            except Exception as e:
                self._log_debug(f"Could not read the power cable state: {e}")
                return None

    def get_power_consumption(self) -> float | None:
        """
        Current power consumption in watts.
        """
        if self._ups_is_mocked:
            return self.MOCKED_POWER_CONSUMPTION_WATTS
        with self._lock:
            watts = PowerReader.power_consumption_watts()
            return None if watts is None else round(watts, 2)

    def get_cpu_amps(self) -> float | None:
        if self._ups_is_mocked:
            return 1.0
        with self._lock:
            return PowerReader.cpu_amps()

    # ---- Thermal and fans ----

    def get_cpu_temperature(self) -> float | None:
        if not self._is_linux:
            return None
        temperature = ThermalReader.cpu_temperature()
        self._publish(SHARED_CPU_TEMPERATURE, temperature)
        return temperature

    def get_cpu_fan_rpm(self) -> int | None:
        if not self._is_linux:
            return None
        rpm = ThermalReader.cpu_fan_rpm()
        self._publish(SHARED_CPU_FAN_RPM, rpm)
        return rpm

    def get_case_fans(self) -> dict[str, float]:
        """
        The speed (0.0 - 1.0) of each case fan by name, as set by FanControl.
        Only the first fans (as many as CASE_FAN_INDEXES) are published to the shared memory.
        """
        if self._fan_control is None:
            return {}
        status = dict(self._fan_control.get_fan_status())
        if len(status) > len(self.CASE_FAN_INDEXES) and not self._warned_about_extra_fans:
            self._warned_about_extra_fans = True
            self._xlog.warning(f"There are {len(status)} case fans but only {len(self.CASE_FAN_INDEXES)} are published to the shared memory.")
        for position, index in enumerate(self.CASE_FAN_INDEXES):
            speed = list(status.values())[position] if position < len(status) else None
            self._publish(index, None if speed is None else round(float(speed), 2))
        return status

    # ---- Helpers ----

    def _publish(self, index: int, value: float | int | None):
        """
        Publishes a value to the shared memory only if it changed. None is published as unknown.
        """
        if self._shared_memory is None:
            return
        value = float(self.UNKNOWN if value is None else value)
        if self._published.get(index) == value:
            return
        try:
            self._shared_memory.write_shared_memory_value(index, value)
            self._published[index] = value
            self._log_debug(f"Published shared value [{index}] = {value}")
        except Exception as e:
            self._xlog.warning(f"Could not publish the shared value [{index}]: {e}")

    def close(self):
        """
        Releases the GPIO pin, if it was claimed.
        """
        with self._lock:
            if self._pld_button is not None:
                try:
                    self._pld_button.close()
                except Exception as e:
                    self._log_debug(f"Could not close the power loss detection pin: {e}")
                self._pld_button = None
