from pitxu.lib.ups.ups import UPS
from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.eink import EinkCanvas

import math

class SystemPowerManagement(PyXavi, Command):

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
        self._xlog.debug(f"🔋 Current UPS battery level: {capacity} % (Voltage: {voltage} V)")
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
    
    def callback_battery_level(self, main_instance, value: any, args: dict = None) -> None:
        """
        Callback for `get_battery_level` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_battery_level`.

        """
        main_instance._xlog.info(f"The battery level in the callback is: {value}")

        try:
            if float(value) < 30.0:
                icon = "🪫"
            else:
                icon = "🔋"

            # New approach, using the existing display instance via main
            main_instance._xlog.error(f"🔋 Showing battery level on eInk: {value}")
            main_instance.show_arbitrary_text_on_eink(
                icon=icon,
                text=f"{value} %",
                font_size=EinkCanvas.FONT_HUGE_SIZE)
        except Exception as e:
            main_instance._xlog.error(f"🛑 Error showing battery level on eInk: {e}")

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_battery_level]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_battery_level":
            return self.callback_battery_level
        return self.default_empty_callback

