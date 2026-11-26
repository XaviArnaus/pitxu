import logging
from subprocess import run

logger = logging.getLogger(__name__)


class DisplayControl:
    """
    Reads and switches the backlight of the Raspberry Pi DSI display (sysfs `bl_power` and `brightness`).

    This is the one actuator of the package. Switching needs sudo.
    """

    DSI_BACKLIGHT_PATH: str = "/sys/class/backlight/11-0045"
    DSI_BACKLIGHT_POWER_PATH: str = DSI_BACKLIGHT_PATH + "/bl_power"
    DSI_BACKLIGHT_BRIGHTNESS_PATH: str = DSI_BACKLIGHT_PATH + "/brightness"
    DSI_BACKLIGHT_MAX_BRIGHTNESS_PATH: str = DSI_BACKLIGHT_PATH + "/max_brightness"

    COMMAND_TIMEOUT_SECONDS: int = 5

    @staticmethod
    def backlight_is_on(path: str = DSI_BACKLIGHT_POWER_PATH) -> bool | None:
        """
        True if the backlight is on, False if off, None if it can't be read.
        """
        try:
            with open(path, "r") as file:
                return file.read().strip() == "0"  # bl_power: 0 = on, 1 = off
        except Exception as e:
            logger.debug(f"Could not read the backlight state [{path}]: {e}")
            return None

    @staticmethod
    def set_backlight(on: bool, path: str = DSI_BACKLIGHT_POWER_PATH) -> bool:
        """
        Switches the backlight. Returns True if the command went through.
        """
        return DisplayControl._write(0 if on else 1, path, "switch the backlight")

    @staticmethod
    def max_brightness(path: str = DSI_BACKLIGHT_MAX_BRIGHTNESS_PATH) -> int | None:
        """
        The highest value that the panel accepts as brightness (255 in the Waveshare 5" DSI), None if it can't be read.
        """
        return DisplayControl._read_int(path, "the maximum brightness")

    @staticmethod
    def brightness(path: str = DSI_BACKLIGHT_BRIGHTNESS_PATH) -> int | None:
        """
        The brightness as the panel knows it (0 to max_brightness()), None if it can't be read.
        """
        return DisplayControl._read_int(path, "the brightness")

    @staticmethod
    def set_brightness(percent: float, path: str = DSI_BACKLIGHT_BRIGHTNESS_PATH,
                       max_path: str = DSI_BACKLIGHT_MAX_BRIGHTNESS_PATH) -> bool:
        """
        Sets the brightness, in percent (0-100, out of range values are clamped). It is independent from the
        backlight switch: with the backlight off, it still has no effect, and it does not turn it on.
        Returns True if the command went through.
        """
        maximum = DisplayControl.max_brightness(max_path)
        if maximum is None:
            return False
        percent = max(0.0, min(100.0, float(percent)))
        return DisplayControl._write(round(maximum * percent / 100), path, "set the brightness")

    @staticmethod
    def _read_int(path: str, what: str) -> int | None:
        try:
            with open(path, "r") as file:
                return int(file.read().strip())
        except Exception as e:
            logger.debug(f"Could not read {what} [{path}]: {e}")
            return None

    @staticmethod
    def _write(value: int, path: str, what: str) -> bool:
        try:
            result = run(["sudo", "-E", "sh", "-c", f"echo {value} > {path}"],
                         capture_output=True, timeout=DisplayControl.COMMAND_TIMEOUT_SECONDS)
            if result.returncode != 0:
                logger.debug(f"Could not {what} ({result.returncode}): {result.stderr.decode(errors='replace').strip()}")
                return False
            return True
        except Exception as e:
            logger.debug(f"Could not {what}: {e}")
            return False
