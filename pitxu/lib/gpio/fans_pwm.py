from __future__ import annotations
from pyxavi import Config, Dictionary, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi

class FansPWM(PyXavi):

    mocked_fans_manager: MockedFans = None
    fans: dict[str, MockedFan] = {}
    fan_pins_per_name: dict[str, int] = {}

    # Configuration
    PWM_GPIO_NR = 18        # PWM gpio number used to drive PWM fan (gpio18 = pin 12)
    WAIT_TIME = 1           # [s] Time to wait between each refresh
    PWM_FREQ = 10000        # [Hz] 10kHz for Noctua PWM control

    # Configurable temperature and fan speed
    MIN_TEMP = 40
    MAX_TEMP = 60
    FAN_LOW = 20
    FAN_HIGH = 100
    FAN_OFF = 0
    FAN_MAX = 100

    # logging and metrics (enable = 1)
    VERBOSE = 0
    NODE_EXPORTER = 0

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(FansPWM, self).init_pyxavi(config=config, params=params)

        self.initialize_fans()

    def initialize_fans(self):
        # Initialise GPIO fans
        self._xlog.info("Initialising GPIO fans...")

        # First of all, in case we are mocked, initialize the singleton that manages the fans
        if self.is_mocked():
            self._xlog.warning("Using mocked GPIO fans")
            self.mocked_fans_manager = MockedFans(config=self._xconfig, params=self._xparams)

        # Gather the definitions from the config and initialise them
        try:
            fan_definitions = self._xconfig.get("gpio.fans.devices", [])
            for fan in fan_definitions:
                self.fans[fan["name"]] = self._new_fan(fan["name"], fan["pin"])
                self.fan_pins_per_name[fan["name"]] = fan["pin"]
        except (Exception, RuntimeError, SystemExit) as e:
            self._xlog.error(f"Error initializing GPIO fans: {e}")
            self._xlog.debug(full_stack())

    def is_on(self, fan_name: str) -> bool:
        if fan_name not in self.fans:
            self._xlog.error(f"Fan '{fan_name}' not defined")
            raise KeyError(f"Fan '{fan_name}' not defined")

        if self.is_mocked():
            return self.mocked_fans_manager.is_lit(pin=self.fan_pins_per_name[fan_name])

        return self.fans[fan_name].is_lit
    
    def turn_on(self, fan_name: str):
        if fan_name not in self.fans:
            self._xlog.error(f"Fan '{fan_name}' not defined")
            raise KeyError(f"Fan '{fan_name}' not defined")

        self.fans[fan_name].on()

    def turn_off(self, fan_name: str):
        if fan_name not in self.fans or self.fans[fan_name] is None:
            self._xlog.error(f"Fan '{fan_name}' not defined")
            raise KeyError(f"Fan '{fan_name}' not defined")

        self.fans[fan_name].off()

    def _new_fan(self, name: str, pin: int) -> MockedFan:
        if self.is_mocked():
            self._xlog.warning(f"Creating mocked fan [{name}] for pin [{pin}]")
            return self.mocked_fans_manager.add_fan(name=name, pin=pin)
        else:
            self._xlog.debug(f"Creating real fan for [{name}] pin {pin}")
            from gpiozero import OutputDevice

            return OutputDevice(pin)
    
    def close(self):
        if not self.is_mocked():
            for fan in self.fans.values():
                fan.close()
    
    def is_mocked(self) -> bool:
        return self._xconfig.get("gpio.mock", False) and self._xconfig.get("gpio.fans.mock", False)
    
    def get_all_fans(self) -> dict[str, MockedFan]:
        return self.fans


class MockedFans(PyXavi):
    """
    Mocking gpiozero.Fan for testing purposes.
    This aims to have a single mocking instance with all mocked fans defined.
    This way we intend to reduce the number of keyboard listeners created.
    This change from having one listener per fan to a single listener for all fans
    fixed the Mac OS issue where more than 2 key listeners provoked "Abort trap: 6" errors.
    """
    fans: dict = {}
    fans_by_pin: dict = {}
    _listener = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(MockedFans, self).init_pyxavi(config=config, params=params)
        self.fans = {}

    def add_fan(self, name: str, pin: int):

        # The value is the initial state of the fan (not pressed)
        self.fans[name] = MockedFan()

        # Now we fill the reverse mapping
        self.fans_by_pin[str(pin)] = name

        return self.fans[name]

    def is_lit(self, pin: int) -> bool:
        if str(pin) not in self.fans_by_pin:
            self._xlog.error(f"Fan with pin '{pin}' not defined in mocked fans")
            raise KeyError(f"Fan with pin '{pin}' not defined in mocked fans")

        key = self.fans_by_pin[str(pin)]
        value = self.fans[key]
        return value

class MockedFan(PyXavi):
    """
    Mocked version of gpiozero.Fan for testing purposes.
    """

    mocked_value: bool = False

    def on(self):
        self.mocked_value = True

    def off(self):
        self.mocked_value = False

    def toggle(self):
        self.mocked_value = not self.mocked_value

    @property
    def is_lit(self) -> bool:
        return self.mocked_value

    @property
    def value(self) -> bool:
        return self.is_lit