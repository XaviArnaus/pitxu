import logging
import struct
from subprocess import run

logger = logging.getLogger(__name__)


class PowerReader:
    """
    Reads power related data:
        - The UPS battery gauge (MAX17048-like fuel gauge on I2C).
        - The Raspberry Pi 5 PMIC ADC through `vcgencmd pmic_read_adc`.

    The I2C bus is opened and closed on every read, so nothing is held between calls.
    """

    I2C_BUS: int = 1
    GAUGE_ADDRESS: int = 0x36
    GAUGE_VCELL_REGISTER: int = 0x02
    GAUGE_SOC_REGISTER: int = 0x04

    COMMAND_TIMEOUT_SECONDS: int = 5

    # ---- UPS battery gauge ----

    @staticmethod
    def battery_voltage_and_capacity(bus: int = I2C_BUS, address: int = GAUGE_ADDRESS) -> tuple[float, float] | None:
        """
        Returns (cell voltage in V, capacity in %), or None if the gauge can't be read.
        """
        try:
            import smbus2

            with smbus2.SMBus(bus) as i2c:
                voltage_read = i2c.read_word_data(address, PowerReader.GAUGE_VCELL_REGISTER)
                capacity_read = i2c.read_word_data(address, PowerReader.GAUGE_SOC_REGISTER)
            # The gauge sends big endian, SMBus reads little endian.
            voltage_swapped = struct.unpack("<H", struct.pack(">H", voltage_read))[0]
            capacity_swapped = struct.unpack("<H", struct.pack(">H", capacity_read))[0]
            return voltage_swapped * 1.25 / 1000 / 16, capacity_swapped / 256
        except Exception as e:
            logger.debug(f"Could not read the battery gauge (bus {bus}, address {hex(address)}): {e}")
            return None

    # ---- Raspberry Pi PMIC ----

    @staticmethod
    def pmic_readings() -> dict[str, float] | None:
        """
        All the PMIC ADC readings in one call, keyed by their label,
        e.g. {"VDD_CORE_A": 0.9, "VDD_CORE_V": 0.72, "EXT5V_V": 5.1, ...}.
        Amperes and volts keep their A / V suffix in the label.
        """
        output = PowerReader._vcgencmd(["pmic_read_adc"])
        if output is None:
            return None
        readings: dict[str, float] = {}
        for line in output.splitlines():
            try:
                # "   VDD_CORE_A current(7)=2.1A"
                parts = line.strip().split()
                if len(parts) < 2:
                    continue
                label = parts[0]
                value = parts[-1].split("=")[1][:-1]
                readings[label] = float(value)
            except (IndexError, ValueError):
                logger.debug(f"Skipping an unparseable PMIC line: [{line}]")
        return readings or None

    @staticmethod
    def cpu_volts() -> float | None:
        return PowerReader._pmic_value("VDD_CORE_V")

    @staticmethod
    def cpu_amps() -> float | None:
        return PowerReader._pmic_value("VDD_CORE_A")

    @staticmethod
    def input_voltage() -> float | None:
        """External 5V input voltage, as seen by the PMIC."""
        return PowerReader._pmic_value("EXT5V_V")

    @staticmethod
    def throttled_flags() -> int | None:
        """
        The raw bit field of `vcgencmd get_throttled` (under-voltage, frequency capping, throttling...).
        Decoding the bits is up to the caller.
        """
        output = PowerReader._vcgencmd(["get_throttled"])
        if output is None:
            return None
        try:
            # "throttled=0x50005"
            return int(output.split("=")[1].strip(), 0)
        except (IndexError, ValueError):
            logger.debug(f"Could not parse the throttled flags: [{output}]")
            return None

    @staticmethod
    def power_consumption_watts() -> float | None:
        """
        Sum of amperes x volts over every rail that has both.
        """
        readings = PowerReader.pmic_readings()
        if readings is None:
            return None
        watts = 0.0
        for label, amps in readings.items():
            if not label.endswith("_A"):
                continue
            volts = readings.get(label[:-2] + "_V")
            if volts is not None:
                watts += amps * volts
        return watts

    # ---- Internals ----

    @staticmethod
    def _pmic_value(label: str) -> float | None:
        readings = PowerReader.pmic_readings()
        return readings.get(label) if readings is not None else None

    @staticmethod
    def _vcgencmd(args: list[str]) -> str | None:
        try:
            result = run(["vcgencmd", *args], capture_output=True, timeout=PowerReader.COMMAND_TIMEOUT_SECONDS)
            if result.returncode != 0:
                logger.debug(f"vcgencmd {' '.join(args)} failed ({result.returncode}): {result.stderr.decode(errors='replace').strip()}")
                return None
            return result.stdout.decode(errors="replace")
        except Exception as e:
            logger.debug(f"vcgencmd {' '.join(args)} could not run: {e}")
            return None
