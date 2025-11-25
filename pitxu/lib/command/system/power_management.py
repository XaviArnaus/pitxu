from subprocess import call
from pitxu.lib.ups.ups import UPS
from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager

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
        try:
            self.close_nicely()
            call("sudo nohup shutdown -h now", shell=True)
        except Exception as e:
            self._xlog.error(f"Error during shutdown: {e}")

    def reboot_local_machine(self):
        '''
        Reboots the local machine. Beware: This will immediately reboot the machine.
        '''
        try:
            self.close_nicely()
            call("sudo nohup reboot", shell=True)
        except Exception as e:
            self._xlog.error(f"Error during reboot: {e}")
    
    def close_nicely(self):
        '''
        Placeholder for any cleanup operations before shutdown or reboot.
        '''
        self._xlog.info("Performing cleanup operations before shutdown/reboot.")
        
        shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        shared_memory.initialize_existing_shared_memory_flags()
        shared_memory.close()

        self.ups.close()

