from __future__ import annotations
from pyxavi import Config, Dictionary, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi

class CpuTemperature(PyXavi):

    device: MockedCpuTemperature = None

    DEFAULT_MIN_TEMPERATURE = 30
    DEFAULT_MAX_TEMPERATURE = 90
    DEFAULT_THRESHOLD = 50
    DEFAULT_SENSOR_FILE = "/sys/class/thermal/thermal_zone0/temp"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(CpuTemperature, self).init_pyxavi(config=config, params=params)

        self.initialize_cpu_temperature()

    def initialize_cpu_temperature(self):
        # Initialise GPIO CPU temperature
        self._xlog.info("Initialising GPIO CPU temperature...")

        # First of all, in case we are mocked we define the Mocked class.
        if self.is_mocked():
            self._xlog.warning("Using mocked GPIO CPU temperature")
            self.device = MockedCpuTemperature(config=self._xconfig, params=self._xparams)

        # Gather the parameters from the config and initialise them
        else:
            from gpiozero import CPUTemperature
            try:
                cpu_temperature_parameters = self._xconfig.get("gpio.cpu_temperature", {})
                self.device = CPUTemperature(
                    min_temp=cpu_temperature_parameters.get("min_temperature", self.DEFAULT_MIN_TEMPERATURE),
                    max_temp=cpu_temperature_parameters.get("max_temperature", self.DEFAULT_MAX_TEMPERATURE),
                    threshold=cpu_temperature_parameters.get("threshold", self.DEFAULT_THRESHOLD),
                    sensor_file=cpu_temperature_parameters.get("sensor_file", self.DEFAULT_SENSOR_FILE)
                )

            except (Exception, RuntimeError, SystemExit) as e:
                self._xlog.error(f"Error initializing GPIO CPU temperature: {e}")
                self._xlog.debug(full_stack())

    def is_above_threshold(self, margin: float = 0) -> bool:
        return self.get_temperature() >= self.get_threshold() + margin
    
    def is_below_threshold(self, margin: float = 0) -> bool:
        return self.get_temperature() <= self.get_threshold() - margin

    def get_temperature(self) -> float:
        return self.device.temperature
    
    def get_threshold(self) -> float:
        return self.device.threshold

    def close(self):
        if self.device is not None and not self.is_mocked():
            self.device.close()

    def is_mocked(self) -> bool:
        return self._xconfig.get("gpio.mock", False) and self._xconfig.get("gpio.cpu_temperature.mock", False)


class MockedCpuTemperature(PyXavi):
    """
    Mocking gpiozero.CPUTemperature for testing purposes.
    This aims to have a single mocking instance with all mocked CPU temperatures defined.
    This way we intend to reduce the number of keyboard listeners created.
    This change from having one listener per CPU temperature to a single listener for all CPU temperatures
    fixed the Mac OS issue where more than 2 key listeners provoked "Abort trap: 6" errors.
    """
    MOCKED_TEMPERATURE = 40

    def __init__(self, config: Config = None, params: Dictionary = None, max_temperature: float = None, min_temperature: float = None, threshold: float = None):
        super(MockedCpuTemperature, self).init_pyxavi(config=config, params=params)
        self.max_temperature = max_temperature if max_temperature is not None else CpuTemperature.DEFAULT_MAX_TEMPERATURE
        self.min_temperature = min_temperature if min_temperature is not None else CpuTemperature.DEFAULT_MIN_TEMPERATURE
        self.threshold = threshold if threshold is not None else CpuTemperature.DEFAULT_THRESHOLD

    @property
    def is_active(self) -> bool:
        return False
    
    @property
    def temperature(self) -> float:
        return self.MOCKED_TEMPERATURE
    
    @property
    def value(self) -> float:
        return self.temperature / 100
    

