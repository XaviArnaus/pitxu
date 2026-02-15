from __future__ import annotations
from pyxavi import Config, Dictionary, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi

class Fans(PyXavi):

    mocked_fans_manager: MockedFans = None
    fans: dict[str, MockedFan] = {}
    fan_pins_per_name: dict[str, int] = {}

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Fans, self).init_pyxavi(config=config, params=params)

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
                self._xlog.info(f"Initializing fan '{fan['name']}' on pin {fan['pin']} with {'PWM' if fan.get('is_pwm', False) else 'no-PWM'} control")
                self.fans[fan["name"]] = self._new_fan(fan["name"], fan["pin"], is_pwm=fan.get("is_pwm", False))
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
    
    def set_speed(self, fan_name: str, speed: float):
        if fan_name not in self.fans or self.fans[fan_name] is None:
            self._xlog.error(f"Fan '{fan_name}' not defined")
            raise KeyError(f"Fan '{fan_name}' not defined")

        if not isinstance(self.fans[fan_name], FanPwm):
            self._xlog.error(f"Fan '{fan_name}' is not a PWM fan, cannot set speed")
            raise TypeError(f"Fan '{fan_name}' is not a PWM fan, cannot set speed")

        self.fans[fan_name].set_speed(speed)

    def _new_fan(self, name: str, pin: int, is_pwm: bool = False) -> MockedFan:
        if self.is_mocked():
            self._xlog.warning(f"Creating mocked fan [{name}] for pin [{pin}] as {'PWM' if is_pwm else 'no-PWM'} fan")
            return self.mocked_fans_manager.add_fan(name=name, pin=pin, is_pwm=is_pwm)
        else:
            self._xlog.debug(f"Creating real fan for [{name}] pin {pin}")
            return FanPwm(name=name, pin=pin) if is_pwm else Fan(name=name, pin=pin)
    
    def close(self):
        if not self.is_mocked():
            for fan in self.fans.values():
                fan.close()
    
    def is_mocked(self) -> bool:
        return self._xconfig.get("gpio.mock", False) and self._xconfig.get("gpio.fans.mock", False)
    
    def get_all_fans(self) -> dict[str, MockedFan]:
        return self.fans
    
    def get(self, fan_name: str) -> MockedFan:
        if fan_name not in self.fans or self.fans[fan_name] is None:
            self._xlog.error(f"Fan '{fan_name}' not defined")
            raise KeyError(f"Fan '{fan_name}' not defined")

        return self.fans[fan_name]
    
    def is_pwm_fan(self, fan_name: str) -> bool:
        if fan_name not in self.fans or self.fans[fan_name] is None:
            self._xlog.error(f"Fan '{fan_name}' not defined")
            raise KeyError(f"Fan '{fan_name}' not defined")

        return isinstance(self.fans[fan_name], FanPwm)
    
class Fan:
    """
    This class is just a wrapper to have a common type for both real and mocked fans.
    It is not intended to be used directly, but rather as a return type for the Fans class.
    """

    name: str
    pin: int

    def __init__(self, name: str, pin: int):
        self.name = name
        self.pin = pin

        self.initialize()

    def initialize(self):
        from gpiozero import OutputDevice

        self.gpio_device = OutputDevice(self.pin)

    def on(self):
        self.gpio_device.on()

    def off(self):
        self.gpio_device.off()

    def toggle(self):
        self.gpio_device.toggle()

    def is_active(self) -> bool:
        return self.gpio_device.is_active

class FanPwm(Fan):
    """
    This class is just a wrapper to have a common type for both real and mocked PWM fans.
    It is not intended to be used directly, but rather as a return type for the Fans class.
    """

    def initialize(self):
        from gpiozero import PWMOutputDevice

        self.gpio_device = PWMOutputDevice(self.pin)
    
    def set_speed(self, speed: float):
        """
        Set the speed of the fan. The speed should be a value between 0 and 1, where 0 is off and 1 is full speed.
        """
        if speed < 0 or speed > 1:
            raise ValueError(f"Invalid speed value '{speed}' for fan '{self.name}'. Speed should be between 0 and 1.")

        self.frequency = speed
    
    @property
    def frequency(self):
        """
        The frequency of the pulses used with the PWM device, in Hz. The
        default is 100Hz.
        """
        return self.gpio_device.frequency

    @frequency.setter
    def frequency(self, value):
        self.gpio_device.frequency = value

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

    def add_fan(self, name: str, pin: int, is_pwm: bool = False) -> MockedFan:

        # The value is the initial state of the fan (not pressed)
        self.fans[name] = MockedFan(name=name, pin=pin) if not is_pwm else MockedFanPwm(name=name, pin=pin)

        # Now we fill the reverse mapping
        self.fans_by_pin[str(pin)] = name

        return self.fans[name]

    def is_active(self, pin: int) -> bool:
        if str(pin) not in self.fans_by_pin:
            self._xlog.error(f"Fan with pin '{pin}' not defined in mocked fans")
            raise KeyError(f"Fan with pin '{pin}' not defined in mocked fans")

        key = self.fans_by_pin[str(pin)]
        value = self.fans[key]
        return value

class MockedFan(Fan):
    """
    Mocked version of gpiozero.Fan for testing purposes.
    """

    def initialize(self):
        pass

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

class MockedFanPwm(FanPwm):
    """
    Mocked version of gpiozero.FanPwm for testing purposes.
    """

    mocked_speed: float = 0

    def initialize(self):
        pass

    def set_speed(self, speed: float):
        self.mocked_speed = speed

    @property
    def frequency(self):
        return self.mocked_speed

    @frequency.setter
    def frequency(self, value):
        self.mocked_speed = value