from gpiozero import Button

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.hardware import PowerReader, ThermalReader

class UPS(PyXavi):
    '''
    Class to manage an Uninterruptible Power Supply (UPS)

    The readings are done by the stateless readers of `lib/hardware`. What stays here is the mock handling,
    the config, and the GPIO pin of the power loss detection (it needs to be claimed, so it can't live in a reader).
    The running app uses the DeviceMonitor instead: this class is for the standalone utilities.
    '''

    CHG_ONOFF_PIN: int = None
    PLD_BUTTON: Button = None
    i2c_address: int = PowerReader.GAUGE_ADDRESS

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

        if self._xconfig.get("ups.mock", True):
            self._xlog.warning("UPS is mocked: Not initialising it.")
        else:
            # Constants
            self.CHG_ONOFF_PIN = 16 # pinctrl get 16
            self.PLD_BUTTON = Button(6) # down = fail, up = pass
            self.i2c_address = int(self._xconfig.get("ups.i2c_address", PowerReader.GAUGE_ADDRESS))

    def read_voltage_and_capacity(self) -> tuple[float, float]:
        if self._xconfig.get("ups.mock", True):
            self._xlog.warning("UPS is mocked: Battery data is fake.")
            return 50, 50

        reading = PowerReader.battery_voltage_and_capacity(address=self.i2c_address)
        if reading is None:
            raise IOError("Could not read the UPS battery gauge")
        return reading

    def get_pld_state(self) -> int:
        if self._xconfig.get("ups.mock", True):
            self._xlog.warning("UPS is mocked: Returning Power Cable always present.")
            return 1

        if self.PLD_BUTTON.is_pressed:
            return 0 # power loss/adapter failure
        else:
            return 1 # power ok

    def is_power_cable_connected(self) -> bool:
        pld_state = self.get_pld_state()
        return pld_state == 1

    def _read_metric(self, reader: callable):
        if self._xconfig.get("ups.mock", True):
            self._xlog.warning("UPS is mocked, Hardware metric data is fake.")
            return 50.2
        return reader()

    def read_cpu_volts(self) -> float:
        return self._read_metric(PowerReader.cpu_volts) # return current cpu voltage

    def read_cpu_amps(self) -> float:
        return self._read_metric(PowerReader.cpu_amps) # reurn current cpu amperage

    def read_cpu_temp(self)-> float:
        return self._read_metric(ThermalReader.cpu_temperature) # return current cpu temp

    def read_input_voltage(self) -> float:
        return self._read_metric(PowerReader.input_voltage) # return input voltage

    def get_fan_rpm(self) -> str:
        if self._xconfig.get("ups.mock", True):
            self._xlog.warning("UPS is mocked: Returning fake fan RPM.")
            return "0 RPM"

        rpm = ThermalReader.cpu_fan_rpm()
        return "No fan?" if rpm is None else f"{rpm} RPM"

    def power_consumption_watts(self) -> float:
        if self._xconfig.get("ups.mock", True):
            self._xlog.warning("UPS is mocked: Power consumption data is fake.")
            return 10.0

        return PowerReader.power_consumption_watts()

    def close(self) -> None:
        '''
        Closes the UPS resources.
        '''
        if self._xconfig.get("ups.mock", True):
            self._xlog.warning("UPS is mocked, Faking close().")
            return

        if self.PLD_BUTTON is not None:
            self.PLD_BUTTON.close()
            self.PLD_BUTTON = None
