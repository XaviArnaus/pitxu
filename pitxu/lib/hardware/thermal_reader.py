import glob
import logging

logger = logging.getLogger(__name__)


class ThermalReader:
    """
    Reads the CPU temperature and the CPU fan speed from sysfs.
    """

    THERMAL_ZONE_PATH: str = "/sys/class/thermal/thermal_zone{zone}/temp"
    HWMON_FAN_PATTERN: str = "/sys/class/hwmon/hwmon*/fan1_input"

    @staticmethod
    def cpu_temperature(zone: int = 0) -> float | None:
        """
        CPU temperature in Celsius, rounded to one decimal.
        """
        try:
            with open(ThermalReader.THERMAL_ZONE_PATH.format(zone=zone), "r") as file:
                return round(int(file.read().strip()) / 1000, 1)
        except Exception as e:
            logger.debug(f"Could not read the temperature of the thermal zone [{zone}]: {e}")
            return None

    @staticmethod
    def cpu_fan_rpm() -> int | None:
        """
        Speed of the CPU fan in RPM, or None if there is no tachometer to read.
        """
        try:
            # The hwmon number changes between boots (hwmon2, hwmon3...), so we look for it.
            paths = sorted(glob.glob(ThermalReader.HWMON_FAN_PATTERN))
            if not paths:
                logger.debug("No fan1_input found under hwmon.")
                return None
            with open(paths[0], "r") as file:
                return int(file.read().strip())
        except Exception as e:
            logger.debug(f"Could not read the CPU fan speed: {e}")
            return None
