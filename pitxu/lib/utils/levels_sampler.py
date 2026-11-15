import platform
import threading
import time

from pyxavi import Config, Dictionary

from definitions import SHARED_MIC_VOLUME, SHARED_SPEAKER_VOLUME, SHARED_BATTERY_LEVEL, \
                        SHARED_SPEAKER_MUTED, SHARED_POWER_CABLE_CONNECTED
from pitxu.lib.abstract.pyxavi import PyXavi


class LevelsSampler(PyXavi):
    """
    Reads the system levels that have no event to follow (volumes, battery, power cable)
    and publishes them in the shared memory values, so any display can show them without asking.

    tick() is meant to be called every second:
        - The power cable is read on every tick (a cheap GPIO read).
        - The volumes and the battery are read once at the beginning, and then every LEVELS_EVERY_SECONDS.
          They need shell calls (amixer) or I2C, so they run in a short daemon thread that never blocks the caller.
    Everything is published as an integer: percentages, or 1 / 0 for the booleans. -1 means unknown.
    Nothing is written unless it changed.
    It reuses the live `volume` and `power_management` instances of the Chatbot Session Manager:
        a second UPS would try to claim the GPIO pin again, and a second SystemVolume resets the mic volume when created.
    """

    LEVELS_EVERY_SECONDS: int = 60
    UNKNOWN: int = -1
    # Shown on the Mac, where the UPS is mocked.
    MOCKED_BATTERY_LEVEL: int = 50

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(LevelsSampler, self).init_pyxavi(config=config, params=params)

        # SharedMemoryManager and a callable returning the dict of clients (resolved on every use).
        self._shared_memory = params.get("shared_memory")
        self._clients_provider = params.get("clients_provider")

        self._ups_is_mocked: bool = bool(self._xconfig.get("ups.mock", True))
        # How to detect the power cable: "gpio" reads the UPS pin, "disabled" always publishes unknown.
        self._power_cable_detection: str = str(self._xconfig.get("ups.power_cable_detection", "gpio")).lower()
        if self._power_cable_detection not in ("gpio", "disabled"):
            self._xlog.warning(f"Unknown ups.power_cable_detection [{self._power_cable_detection}], using 'gpio'.")
            self._power_cable_detection = "gpio"
        self._last_levels_sampled_at: float | None = None
        self._levels_thread: threading.Thread | None = None
        self._published: dict[int, int] = {}

    def tick(self):
        """
        To be called every second.
        """
        try:
            self._sample_power_cable()

            levels_are_due = self._last_levels_sampled_at is None or \
                (time.monotonic() - self._last_levels_sampled_at) >= self.LEVELS_EVERY_SECONDS
            levels_are_running = self._levels_thread is not None and self._levels_thread.is_alive()

            if levels_are_due and not levels_are_running:
                self._last_levels_sampled_at = time.monotonic()
                self._levels_thread = threading.Thread(target=self._sample_levels, name="LevelsSampler", daemon=True)
                self._levels_thread.start()
        except Exception as e:
            self._xlog.warning(f"LevelsSampler tick failed: {e}")

    # ---- Sampling ----

    def _sample_power_cable(self):
        if self._power_cable_detection == "disabled":
            # Not trustworthy (or not wanted): publish it as unknown, so the display does not claim anything.
            self._publish_value(SHARED_POWER_CABLE_CONNECTED, self.UNKNOWN)
            return
        if self._ups_is_mocked:
            # The UPS class logs a warning on every read when mocked, so we don't read it at all.
            self._publish_value(SHARED_POWER_CABLE_CONNECTED, 1)
            return

        power_management = self._get_client("power_management")
        if power_management is None:
            return
        try:
            self._publish_value(SHARED_POWER_CABLE_CONNECTED, 1 if power_management.is_power_cable_connected() else 0)
        except Exception as e:
            self._log_debug(f"Could not read the power cable state: {e}")

    def _sample_levels(self):
        try:
            volume = self._get_client("volume")
            power_management = self._get_client("power_management")

            if volume is None and power_management is None:
                # The Chatbot Session Manager is not there yet. Try again on the next tick instead of waiting a minute.
                self._last_levels_sampled_at = None
                return

            # The volume functions only work on Linux with ALSA (and warn otherwise), so we leave the values as unknown.
            if volume is not None and platform.system() == "Linux":
                self._publish_value(SHARED_MIC_VOLUME, self._read_int(volume.get_local_system_microphone_volume_level))
                self._publish_value(SHARED_SPEAKER_VOLUME, self._read_int(volume.get_local_system_speaker_volume_level))
                muted = self._read(volume.get_local_system_speaker_mute_status)
                # It returns -1 when it can't read it, so only a real True or False counts.
                self._publish_value(SHARED_SPEAKER_MUTED, 1 if muted is True else 0 if muted is False else self.UNKNOWN)

            if power_management is not None:
                if self._ups_is_mocked:
                    self._publish_value(SHARED_BATTERY_LEVEL, self.MOCKED_BATTERY_LEVEL)
                else:
                    self._publish_value(SHARED_BATTERY_LEVEL, self._read_int(power_management.get_battery_level))
        except Exception as e:
            self._xlog.warning(f"LevelsSampler could not sample the levels: {e}")

    # ---- Helpers ----

    def _get_client(self, name: str):
        try:
            clients = self._clients_provider() if self._clients_provider is not None else {}
            return clients.get(name, None)
        except Exception:
            return None

    def _read(self, function: callable):
        try:
            return function()
        except Exception as e:
            self._log_debug(f"Could not read a level: {e}")
            return None

    def _read_int(self, function: callable) -> int:
        value = self._read(function)
        try:
            return int(round(value)) if value is not None else self.UNKNOWN
        except (TypeError, ValueError):
            return self.UNKNOWN

    def _publish_value(self, index: int, value: int):
        if self._published.get(index) == value:
            return
        self._shared_memory.write_shared_memory_value(index, float(value))
        self._published[index] = value
        self._log_debug(f"Published shared value [{index}] = {value}")