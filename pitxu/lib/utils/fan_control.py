from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.gpio.fans import Fans
from pitxu.lib.gpio.cpu_temperature import CpuTemperature

class FanControl(PyXavi):

    MARGIN_THRESHOLD_DEGREES_TEMP = 10

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(FanControl, self).init_pyxavi(config=config, params=params)

        self.fans = Fans(config=config, params=params)
        self.cpu_temperature = CpuTemperature(config=config, params=params)

        self.MARGIN_THRESHOLD_DEGREES_TEMP = self._xconfig.get("gpio.cpu_temperature.margin", self.MARGIN_THRESHOLD_DEGREES_TEMP)
    
    def toggle_all_fans_by_temperature(self):
        for fan_name in self.fans.get_all_fans().keys():
            self.toggle_fan_by_temperature(fan_name=fan_name)
    
    def toggle_fan_by_temperature(self, fan_name: str):

        if self.cpu_temperature.is_above_threshold():
            self._log_debug(f"CPU temperature {self.cpu_temperature.get_temperature()}°C is above threshold, turning on fan '{fan_name}'")
            self.fans.turn_on(fan_name=fan_name)

        elif self.cpu_temperature.is_below_threshold(margin=self.MARGIN_THRESHOLD_DEGREES_TEMP):
            self._log_debug(f"CPU temperature {self.cpu_temperature.get_temperature()}°C is below threshold (minus margin of {self.MARGIN_THRESHOLD_DEGREES_TEMP}°C), turning off fan '{fan_name}'")
            self.fans.turn_off(fan_name=fan_name)
