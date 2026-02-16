from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.gpio.fans import Fans
from pitxu.lib.gpio.cpu_temperature import CpuTemperature

class FanControl(PyXavi):

    # TODO: Maybe rework it with PWM control (our fans are PWM!) and not just on/off
    # https://github.com/tedsluis/raspberry-pi-pwm-fan-control/blob/main/fan.py

    MAX_TEMPERATURE = 90
    MIN_TEMPERATURE = 30

    MARGIN_THRESHOLD_DEGREES_TEMP = 10

    PWM_FAN_SPEED_25_THRESHOLD = 50
    PWM_FAN_SPEED_50_THRESHOLD = 70
    PWM_FAN_SPEED_75_THRESHOLD = 80

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(FanControl, self).init_pyxavi(config=config, params=params)

        self.fans = Fans(config=config, params=params)
        self.cpu_temperature = CpuTemperature(config=config, params=params)

        self.MARGIN_THRESHOLD_DEGREES_TEMP = self._xconfig.get("gpio.cpu_temperature.margin", self.MARGIN_THRESHOLD_DEGREES_TEMP)
        self.PWM_FAN_SPEED_25_THRESHOLD = self._xconfig.get("gpio.cpu_temperature.pwm_thresholds.threshold_25", self.PWM_FAN_SPEED_25_THRESHOLD)
        self.PWM_FAN_SPEED_50_THRESHOLD = self._xconfig.get("gpio.cpu_temperature.pwm_thresholds.threshold_50", self.PWM_FAN_SPEED_50_THRESHOLD)
        self.PWM_FAN_SPEED_75_THRESHOLD = self._xconfig.get("gpio.cpu_temperature.pwm_thresholds.threshold_75", self.PWM_FAN_SPEED_75_THRESHOLD)
        self.MAX_TEMPERATURE = self._xconfig.get("gpio.cpu_temperature.max_temperature", self.MAX_TEMPERATURE)
        self.MIN_TEMPERATURE = self._xconfig.get("gpio.cpu_temperature.min_temperature", self.MIN_TEMPERATURE)

    def toggle_all_fans_by_temperature(self):

        # Getting the temperature once and then passing it to each fan
        #   to avoid reading the temperature multiple times in a short period of time.
        # Otherwise, when we have multiple fans, the second read may be already different and may not
        #   fulfil the same conditions as the first read, which may cause some fans to be turned on and others not.
        current_cpu_temp = self.cpu_temperature.get_temperature()

        for fan_name in self.fans.get_all_fans().keys():
            self.toggle_fan_by_temperature(fan_name=fan_name, current_cpu_temp=current_cpu_temp)

    def toggle_fan_by_temperature(self, fan_name: str, current_cpu_temp: float = None):

        current_temperature = current_cpu_temp if current_cpu_temp is not None else self.cpu_temperature.get_temperature()

        # We behave different if the fan is PWM or not.
        if self.fans.is_pwm_fan(fan_name=fan_name):
            if current_temperature >= self.MAX_TEMPERATURE:
                self._log_debug(f"CPU temperature {current_temperature}°C is above or equal to max temperature of {self.MAX_TEMPERATURE}°C, setting fan '{fan_name}' to 100% speed")
                self.fans.set_speed(fan_name=fan_name, speed=1.0)
            elif current_temperature >= self.PWM_FAN_SPEED_75_THRESHOLD:
                self._log_debug(f"CPU temperature {current_temperature}°C is above or equal to threshold of {self.PWM_FAN_SPEED_75_THRESHOLD}°C, setting fan '{fan_name}' to 75% speed")
                self.fans.set_speed(fan_name=fan_name, speed=0.75)
            elif current_temperature >= self.PWM_FAN_SPEED_50_THRESHOLD:
                self._log_debug(f"CPU temperature {current_temperature}°C is above or equal to threshold of {self.PWM_FAN_SPEED_50_THRESHOLD}°C, setting fan '{fan_name}' to 50% speed")
                self.fans.set_speed(fan_name=fan_name, speed=0.5)
            elif current_temperature >= self.PWM_FAN_SPEED_25_THRESHOLD:
                self._log_debug(f"CPU temperature {current_temperature}°C is above or equal to threshold of {self.PWM_FAN_SPEED_25_THRESHOLD}°C, setting fan '{fan_name}' to 25% speed")
                self.fans.set_speed(fan_name=fan_name, speed=0.25)
            else:
                self._log_debug(f"CPU temperature {current_temperature}°C is below threshold of {self.PWM_FAN_SPEED_25_THRESHOLD}°C, turning off fan '{fan_name}'")
                self.fans.set_speed(fan_name=fan_name, speed=0.0)

            self._log_debug(f"Fan '{fan_name}' speed set to {self.fans.get(fan_name=fan_name).get_value() * 100}% at {self.fans.get_frequency(fan_name=fan_name)}Hz")

        else:

            if not self.fans.is_on(fan_name=fan_name) and current_temperature >= self.cpu_temperature.get_threshold():
                self._log_debug(f"CPU temperature {current_temperature}°C is above or equal to threshold, turning on fan '{fan_name}'")
                self.fans.turn_on(fan_name=fan_name)

            elif self.fans.is_on(fan_name=fan_name) and current_temperature <= self.cpu_temperature.get_threshold() - self.MARGIN_THRESHOLD_DEGREES_TEMP:
                self._log_debug(f"CPU temperature {current_temperature}°C is below or equal to threshold (minus margin of {self.MARGIN_THRESHOLD_DEGREES_TEMP}°C), turning off fan '{fan_name}'")
                self.fans.turn_off(fan_name=fan_name)
