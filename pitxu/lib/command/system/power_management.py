from subprocess import call
from pitxu.lib.ups.ups import UPS
from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi

import math

class SystemPowerManagement(PyXavi):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

    def get_battery_level(self) -> str:
        '''
        Gets the current battery level

        Returns:
            The current battery level as a percentage
        '''
        voltage, capacity = UPS.read_voltage_and_capacity(UPS.bus)
        return math.ceil(capacity)

    def is_power_cable_connected(self) -> bool:
        '''
        Checks if the power cable is connected

        Returns:
            True if the power cable is connected, False otherwise
        '''
        return UPS.is_power_cable_connected()
    

    def shutdown_local_machine(self, safe_close_callback = None):
        '''
        Shuts down the local machine. Beware: This will immediately power off the machine.
        '''
        try:
            if safe_close_callback is not None:
                safe_close_callback()
            call("sudo nohup shutdown -h now", shell=True)
        except Exception as e:
            self._xlog.error(f"Error during shutdown: {e}")

    def reboot_local_machine(self, safe_close_callback = None):
        '''
        Reboots the local machine. Beware: This will immediately reboot the machine.
        '''
        try:
            if safe_close_callback is not None:
                safe_close_callback()
            call("sudo nohup reboot", shell=True)
        except Exception as e:
            self._xlog.error(f"Error during reboot: {e}")
