import logging
from subprocess import run

logger = logging.getLogger(__name__)


class DisplayControl:
    """
    Reads and switches the backlight of the Raspberry Pi DSI display (sysfs `bl_power`).

    This is the one actuator of the package. Switching needs sudo.
    """

    DSI_BACKLIGHT_POWER_PATH: str = "/sys/class/backlight/11-0045/bl_power"

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
        try:
            result = run(["sudo", "-E", "sh", "-c", f"echo {0 if on else 1} > {path}"],
                         capture_output=True, timeout=DisplayControl.COMMAND_TIMEOUT_SECONDS)
            if result.returncode != 0:
                logger.debug(f"Could not switch the backlight ({result.returncode}): {result.stderr.decode(errors='replace').strip()}")
                return False
            return True
        except Exception as e:
            logger.debug(f"Could not switch the backlight: {e}")
            return False
