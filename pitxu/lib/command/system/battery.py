from pitxu.lib.ups.ups import UPS

class SystemBattery:

    @staticmethod
    def get_battery_level() -> str:
        '''
        Gets the current battery level

        Returns:
            The current battery level as a percentage
        '''
        voltage, capacity = UPS.read_voltage_and_capacity(UPS.bus)
        return capacity