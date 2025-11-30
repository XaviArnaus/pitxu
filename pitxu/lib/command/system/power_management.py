from pitxu.lib.ups.ups import UPS
from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi

import math

class SystemPowerManagement(PyXavi):

    ups: UPS = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

        self.ups = UPS(config=config, params=params)

    def get_battery_level(self) -> str:
        '''
        Gets the current battery level

        Returns:
            The current battery level as a percentage
        '''
        voltage, capacity = self.ups.read_voltage_and_capacity()
        return math.ceil(capacity)

    def is_power_cable_connected(self) -> bool:
        '''
        Checks if the power cable is connected

        Returns:
            True if the power cable is connected, False otherwise
        '''
        return self.ups.is_power_cable_connected()
    

    def shutdown_local_machine(self):
        '''
        Shuts down the local machine. Beware: This will immediately power off the machine.
        '''
        # We fake this command, so that the `main` can handle the actual shutdown
        return True

    def reboot_local_machine(self):
        '''
        Reboots the local machine. Beware: This will immediately reboot the machine.
        '''
        # We fake this command, so that the `main` can handle the actual reboot
        return True

