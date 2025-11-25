from subprocess import call
from pitxu.lib.ups.ups import UPS

import math

class SystemPowerManagement:

    @staticmethod
    def get_battery_level() -> str:
        '''
        Gets the current battery level

        Returns:
            The current battery level as a percentage
        '''
        voltage, capacity = UPS.read_voltage_and_capacity(UPS.bus)
        return math.ceil(capacity)

    @staticmethod
    def is_power_cable_connected() -> bool:
        '''
        Checks if the power cable is connected

        Returns:
            True if the power cable is connected, False otherwise
        '''
        return UPS.is_power_cable_connected()
    
    @staticmethod
    def shutdown_local_machine(safe_close_callback = None):
        '''
        Shuts down the local machine. Beware: This will immediately power off the machine.
        '''
        if safe_close_callback is not None:
            safe_close_callback()
        call("sudo nohup shutdown -h now", shell=True)
    
    @staticmethod
    def reboot_local_machine(safe_close_callback = None):
        '''
        Reboots the local machine. Beware: This will immediately reboot the machine.
        '''
        if safe_close_callback is not None:
            safe_close_callback()
        call("sudo nohup reboot", shell=True)
