from __future__ import annotations
from pyxavi import Config, Dictionary, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi

# PWM control is pretty tricky.
#   1. Implemented using gpiozero's PWMOutputDevice, it is Software PWM, and feels like it has issues:
#       - I can't make it work over 10KHz: Bad PWM whatever (I don't remember the error)
#       - The fans produce very annoying electrical noise. Research tells this is because of wrong frequency.
#           - Tested with 25 Hz, 50 Hz, 83 Hz, 100 Hz, 1kHz, 8kHz, 9kHz and 10 kHz, and all of them produce noise. 
#             The lower the frequency, the noisier the sound.
#
#   2. Implemented using rpi_hardware_pwm, it is Hardware PWM.
#       - Resources:
#           - https://github.com/Pioreactor/rpi_hardware_pwm
#           - https://github.com/Pioreactor/rpi_hardware_pwm/issues/10#issuecomment-2500952367
#           - https://github.com/jdimpson/syspwm
#           - https://gist.github.com/Gadgetoid/b92ad3db06ff8c264eef2abf0e09d569
#       - Usefull commands:
#           $ pinctrl get | grep PWM -> get shell information about the pins and their capabilities, then filter for PWM
#           $ pinctrl funcs 12-13,18-19 -> get the functions that can be used in the pins 12, 13, 18 and 19, which are the PWM ones
#           $ sudo cat /sys/kernel/debug/pwm -> get information about the PWM channels and their state
#           $ find /proc/device-tree -name "*pwm*" -> Check if an overlay was loaded with the "pwm" string in it.

class Fans(PyXavi):

    mocked_fans_manager: MockedFans = None
    fans: dict[str, MockedFan] = {}
    fan_pins_per_name: dict[str, int] = {}

    VERBOSE_DEBUG: bool = True

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
                fan_config = FanConfig.from_dict(fan)
                self._xlog.info(f"Initializing fan '{fan_config.name}' on pin {fan_config.pin} with {'PWM' if fan_config.is_pwm else 'no-PWM'} control{', at frequency ' + str(fan_config.pwm_frequency) if fan_config.is_pwm else 'N/A'}")
                self.fans[fan_config.name] = self._new_fan(fan_config.name, fan_config)
                self.fan_pins_per_name[fan_config.name] = fan_config.pin
        except (Exception, RuntimeError, SystemExit) as e:
            self._xlog.error(f"Error initializing GPIO fans: {e}")
            self._xlog.debug(full_stack())

    def is_on(self, fan_name: str) -> bool:
        if fan_name not in self.fans or self.fans[fan_name] is None:
            self._xlog.error(f"Fan '{fan_name}' not defined")
            raise KeyError(f"Fan '{fan_name}' not defined")

        fan = self.get(fan_name=fan_name)
        return fan.is_active()

    def get_frequency(self, fan_name: str) -> float:
        if fan_name not in self.fans or self.fans[fan_name] is None:
            self._xlog.error(f"Fan '{fan_name}' not defined")
            raise KeyError(f"Fan '{fan_name}' not defined")
        
        if not isinstance(self.fans[fan_name], FanPwm):
            self._xlog.error(f"Fan '{fan_name}' is not a PWM fan, cannot get frequency")
            raise TypeError(f"Fan '{fan_name}' is not a PWM fan, cannot get frequency")

        return self.fans.get(fan_name).frequency

    def turn_on(self, fan_name: str):
        if fan_name not in self.fans:
            self._xlog.error(f"Fan '{fan_name}' not defined")
            raise KeyError(f"Fan '{fan_name}' not defined")

        self._xlog.debug(f"Turning on fan '{fan_name}'")
        self.fans[fan_name].on()

    def turn_off(self, fan_name: str):
        if fan_name not in self.fans or self.fans[fan_name] is None:
            self._xlog.error(f"Fan '{fan_name}' not defined")
            raise KeyError(f"Fan '{fan_name}' not defined")

        self._xlog.debug(f"Turning off fan '{fan_name}'")
        self.fans[fan_name].off()
    
    def set_speed(self, fan_name: str, speed: float):
        if fan_name not in self.fans or self.fans[fan_name] is None:
            self._xlog.error(f"Fan '{fan_name}' not defined")
            raise KeyError(f"Fan '{fan_name}' not defined")

        if not isinstance(self.fans[fan_name], FanPwm):
            self._xlog.error(f"Fan '{fan_name}' is not a PWM fan, cannot set speed")
            raise TypeError(f"Fan '{fan_name}' is not a PWM fan, cannot set speed")

        self._xlog.debug(f"Setting speed of fan '{fan_name}' to {speed}")
        self.fans[fan_name].set_speed(speed)

    def _new_fan(self, name: str, fan_config: FanConfig) -> MockedFan:
        if self.is_mocked():
            self._xlog.warning(f"Creating mocked fan [{name}] for pin [{fan_config.pin}] as {'PWM' if fan_config.is_pwm else 'no-PWM'} fan")
            return self.mocked_fans_manager.add_fan(name=name, fan_config=fan_config)
        else:
            self._xlog.warning(f"Creating real fan [{name}] for pin [{fan_config.pin}] as {'PWM' if fan_config.is_pwm else 'no-PWM'} fan")
            try:
                if fan_config.is_pwm:
                    return FanPwm(config=self._xconfig, params=self._xparams, fan_config=fan_config)
                else:
                    return Fan(config=self._xconfig, params=self._xparams, fan_config=fan_config)
            except RuntimeError as e:
                self._xlog.warning(f"Falling back to a non-PWM fan for fan '{name}' at pin [{fan_config.pin}] due to error: {e}")
                return Fan(config=self._xconfig, params=self._xparams, fan_config=fan_config)

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
    
class Fan(PyXavi):
    """
    Base definition for a Fan. It gets extended to implement PWM and mocked fans.
    """

    fan_config: FanConfig = None

    def __init__(self, config: Config, params: Dictionary, fan_config: FanConfig):
        super().init_pyxavi(config=config, params=params)

        self.fan_config = fan_config

        self.initialize()

    def initialize(self):
        from gpiozero import OutputDevice

        self.gpio_device = OutputDevice(self.fan_config.pin, initial_value=False)

    def on(self):
        self.gpio_device.on()

    def off(self):
        self.gpio_device.off()

    def toggle(self):
        self.gpio_device.toggle()

    def is_active(self) -> bool:
        return self.gpio_device.is_active
    
    def get_value(self) -> bool:
        return self.gpio_device.value

class FanPwm(Fan):
    """
    This class is just a wrapper to have a common type for both real and mocked PWM fans.
    """

    # The frequency of the pulses used with the PWM device, in Hz. The default is 100Hz.
    #   5000 RPM Fan is around 83.33 Hz
    FAN_FREQUENCY: float = 100

    # The HardwarePWM implementation does not read values. We need to hold the last set() and return that instead.
    active: bool = False
    frequency_value: float = FAN_FREQUENCY
    duty_cycle_value: float = 0


    def __init__(self, config: Config, params: Dictionary, fan_config: FanConfig):
        
        super(FanPwm, self).__init__(config=config, params=params, fan_config=fan_config)

        if fan_config.pwm_frequency is not None:
            self.FAN_FREQUENCY = fan_config.pwm_frequency

    def initialize(self):
        # from gpiozero import PWMOutputDevice

        # dd(self.FAN_FREQUENCY)
        # self.gpio_device = PWMOutputDevice(self.pin, initial_value=0, frequency=self.FAN_FREQUENCY)
        from rpi_hardware_pwm import HardwarePWM, HardwarePWMException

        try:
            self.gpio_device = HardwarePWM(
                pwm_channel=self.fan_config.pwm_channel, 
                hz=self.FAN_FREQUENCY, 
                chip=self.fan_config.pwm_chip)

            self.gpio_device.start(initial_duty_cycle=0)
        except HardwarePWMException as e:
            error_message = f"Error initializing PWM fan '{self.fan_config.name}' on pin {self.fan_config.pin}: {e}"
            self._xlog.error(error_message)
            self._xlog.debug(full_stack())
            raise RuntimeError(error_message)

        # Now the control statuses
        self.frequency_value = self.FAN_FREQUENCY
        self.duty_cycle_value = 0

    def set_speed(self, speed: float):
        """
        Set the speed of the fan. The speed should be a value between 0 and 1, where 0 is off and 1 is full speed.
        """
        speed = float(speed)
        if speed < 0 or speed > 1:
            raise ValueError(f"Invalid speed value '{speed}' for fan '{self.fan_config.name}'. Speed should be between 0 and 1.")

        # The rpi_hardware_pwm library uses duty cycle in percentage, so we need to convert the speed to percentage.
        self.gpio_device.change_duty_cycle(speed * 100)
        self.duty_cycle_value = speed
    
    @property
    def frequency(self):
        """
        The frequency of the pulses used with the PWM device, in Hz. The
        default is 100Hz.
        """
        return self.frequency_value

    @frequency.setter
    def frequency(self, value):
        self.set_speed(value)
        self.frequency_value = value
    
    def get_value(self) -> float:
        return self.duty_cycle_value
    
    def is_active(self) -> bool:
        return self.duty_cycle_value > 0

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

    def add_fan(self, name: str, fan_config: FanConfig) -> MockedFan:

        # The value is the initial state of the fan (not pressed)
        if not fan_config.is_pwm:
            self.fans[name] = MockedFan(config=self._xconfig, params=self._xparams, fan_config=fan_config)
        else:
            self.fans[name] = MockedFanPwm(config=self._xconfig, params=self._xparams, fan_config=fan_config)

        # Now we fill the reverse mapping
        self.fans_by_pin[str(fan_config.pin)] = name

        return self.fans[name]
    
    def get_fan(self, name: str) -> MockedFan:
        if name not in self.fans or self.fans[name] is None:
            self._xlog.error(f"Fan '{name}' not defined in mocked fans")
            raise KeyError(f"Fan '{name}' not defined in mocked fans")

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
    
    def is_active(self) -> bool:
        return self.mocked_value

class MockedFanPwm(FanPwm):
    """
    Mocked version of gpiozero.FanPwm for testing purposes.
    """

    mocked_speed: float = 0

    def __init__(self, config: Config, params: Dictionary, fan_config: FanConfig):
        super(MockedFanPwm, self).__init__(config=config, params=params, fan_config=fan_config)

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
    
    def get_value(self) -> float:
        return self.mocked_speed
    
    def is_active(self) -> bool:
        return self.mocked_speed > 0

class FanConfig:

    name: str
    is_pwm: bool
    pin: int
    pwm_frequency: int = None
    pwm_chip: int = None
    pwm_channel: int = None

    def __init__(self, name: str, is_pwm: bool, pin: int, pwm_frequency: int = None, pwm_chip: int = None, pwm_channel: int = None):
        self.name = name
        self.is_pwm = is_pwm
        self.pin = pin
        self.pwm_frequency = pwm_frequency
        self.pwm_chip = pwm_chip
        self.pwm_channel = pwm_channel

    @staticmethod
    def from_dict(config: dict) -> FanConfig:
        return FanConfig(
            name=config.get("name"),
            is_pwm=config.get("is_pwm", False),
            pin=config.get("pin"),
            pwm_frequency=config.get("pwm_frequency"),
            pwm_chip=config.get("chip"),
            pwm_channel=config.get("channel")
        )