from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.gpio.fans import Fans
from pitxu.lib.gpio.cpu_temperature import CpuTemperature

class FanControl(PyXavi):
    
    def __init__(self, config: Config = None, params: Dictionary = None):
        super(FanControl, self).init_pyxavi(config=config, params=params)

        self.fans = Fans(config=config, params=params)
        self.cpu_temperature = CpuTemperature(config=config, params=params)
    
    def toggle_all_fans_by_temperature(self):
        for fan_name in self.fans.get_all_fans().keys():
            self.toggle_fan_by_temperature(fan_name=fan_name)
    
    def toggle_fan_by_temperature(self, fan_name: str):
        if self.cpu_temperature.is_above_threshold():
            self._log_debug(f"CPU temperature {self.cpu_temperature.get_temperature('cpu')}°C is above threshold, turning on fan '{fan_name}'")
            self.fans.turn_on(fan_name=fan_name)
        else:
            self._log_debug(f"CPU temperature {self.cpu_temperature.get_temperature('cpu')}°C is below threshold, turning off fan '{fan_name}'")
            self.fans.turn_off(fan_name=fan_name)
