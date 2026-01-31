from pitxu.lib.ups.ups import UPS
from pyxavi import Config, Dictionary, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.canvas.canvas import Canvas

from subprocess import check_output

import logging

import math

class SystemPowerManagement(PyXavi, Command):

    ups: UPS = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

        self.ups = UPS(config=config, params=params)

    def get_battery_level(self) -> int:
        '''
        Get the current battery level

        Returns:
            int: The current battery level as a percentage
        '''
        try:
            max_retries = 2
            retries = 0
            while retries < max_retries:
                try:
                    voltage, capacity = self.ups.read_voltage_and_capacity()
                    break
                except Exception as e:
                    retries += 1
                    self._xlog.warning(f"⚠️ Retry {retries}/{max_retries} reading UPS battery level due to error: {e}")
                    if retries >= max_retries:
                        raise e
            self._xlog.debug(f"🔋 Current UPS battery level: {capacity} % (Voltage: {voltage} V)")
            return math.ceil(capacity)
        except Exception as e:
            self._xlog.error(f"🛑 Error getting UPS battery level: {e}")
            self._xlog.debug(full_stack())
            return -1

    def is_power_cable_connected(self) -> bool:
        '''
        Check if the power cable is connected

        Returns:
            bool: True if the power cable is connected, False otherwise
        '''
        return self.ups.is_power_cable_connected()

    def get_system_temperature_and_fan_speed(self) -> dict:
        '''
        Get the current system temperature and fan speed.

        Returns:
            dict: A dictionary with 'temperature' in Celsius and 'fan_speed' in RPM.
        '''
        try:
            temperature = round(int(check_output("cat /sys/class/thermal/thermal_zone*/temp", shell=True).decode()) / 1000, 1)
            fan_speed = int(check_output("cat /sys/class/hwmon/hwmon*/fan1_input", shell=True).decode())
            self._log_debug(f"🌡️ Current system temperature: {temperature} °C, Fan speed: {fan_speed} RPM")
            return {
                "temperature": temperature,
                "fan_speed": fan_speed
            }
        except Exception as e:
            self._xlog.error(f"🛑 Error getting system temperature and fan speed: {e}")
            self._xlog.debug(full_stack())
            return {
                "temperature": -1,
                "fan_speed": -1
            }
    
    def callback_system_temperature_and_fan_speed(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_system_temperature_and_fan_speed` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_system_temperature_and_fan_speed`.

        """
        try:
            temperature = value.get("temperature", -1)
            fan_speed = value.get("fan_speed", -1)
            text = f"{temperature} °C\n{fan_speed} RPM"
            font_size = interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE

            if temperature == -1 or fan_speed == -1:
                text = "❌ Error reading values"
                font_size = interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG

            log.info(f"🌡️ Showing system temperature and fan speed on Foreground display: {temperature} °C, {fan_speed} RPM")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="🌡️",
                text=text,
                font_size=font_size
            )
        except Exception as e:
            log.error(f"🛑 Error showing system temperature and fan speed on Foreground display: {e}")


    def shutdown_local_machine(self):
        '''
        Shut down the local machine.
        
        Beware: This will immediately power off the machine.
        Ask always for confirmation before calling this method.
        '''
        # We fake this command, so that the `main` can handle the actual shutdown
        return True

    def reboot_local_machine(self):
        '''
        Reboot the local machine.
        
        Beware: This will immediately reboot the machine.
        Ask always for confirmation before calling this method.
        '''
        # We fake this command, so that the `main` can handle the actual reboot
        return True
    
    def restart_system(self):
        '''
        Restart the system services without rebooting the machine.
        '''
        # We fake this command, so that the `main` can handle the actual restart
        return True
    
    def callback_battery_level(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_battery_level` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_battery_level`.

        """
        log.info(f"The battery level in the callback is: {value}")

        try:
            if float(value) < 30.0:
                icon = "🪫"
            else:
                icon = "🔋"

            # New approach, using the existing display instance via main
            log.error(f"🔋 Showing battery level on Foreground display: {value}")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon=icon,
                text=f"{value} %",
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing battery level on Foreground display: {e}")

    def callback_power_cable_connected(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_power_cable_connected` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_power_cable_connected`.

        """
        try:
            if bool(value):
                icon = "🔌"
            else:
                icon = "❌"
            # New approach, using the existing display instance via main
            log.info(f"🔌 Showing Power Cable Connected: {value}")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon=icon,
                text=f"{'Connected' if value else 'Disconnected'}",
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing power cable connected status on eInk: {e}")

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_battery_level,
                self.is_power_cable_connected,
                self.shutdown_local_machine,
                self.reboot_local_machine,
                self.restart_system,
                self.get_system_temperature_and_fan_speed]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_battery_level":
            return self.callback_battery_level
        elif function_name == "is_power_cable_connected":
            return self.callback_power_cable_connected
        elif function_name == "get_system_temperature_and_fan_speed":
            return self.callback_system_temperature_and_fan_speed
        return self.default_empty_callback

# 2026-01-11 17:55:35,326 [MainProcess ] ERROR    pitxu        🛑 Error getting UPS battery level: [Errno 121] Remote I/O error
# Jan 11 17:55:35 pitxu poetry[4847]: 2026-01-11 17:55:35,332 [MainProcess ] DEBUG    pitxu        Traceback (most recent call last):
# Jan 11 17:55:35 pitxu poetry[4847]:   File "/usr/lib/python3.13/threading.py", line 1014, in _bootstrap
# Jan 11 17:55:35 pitxu poetry[4847]:     self._bootstrap_inner()
# Jan 11 17:55:35 pitxu poetry[4847]:   File "/usr/lib/python3.13/threading.py", line 1043, in _bootstrap_inner
# Jan 11 17:55:35 pitxu poetry[4847]:     self.run()
# Jan 11 17:55:35 pitxu poetry[4847]:   File "/usr/lib/python3.13/threading.py", line 994, in run
# Jan 11 17:55:35 pitxu poetry[4847]:     self._target(*self._args, **self._kwargs)
# Jan 11 17:55:35 pitxu poetry[4847]:   File "/usr/lib/python3.13/concurrent/futures/thread.py", line 93, in _worker
# Jan 11 17:55:35 pitxu poetry[4847]:     work_item.run()
# Jan 11 17:55:35 pitxu poetry[4847]:   File "/usr/lib/python3.13/concurrent/futures/thread.py", line 59, in run
# Jan 11 17:55:35 pitxu poetry[4847]:     result = self.fn(*self.args, **self.kwargs)
# Jan 11 17:55:35 pitxu poetry[4847]:   File "/home/xavier/.cache/pypoetry/virtualenvs/pitxu-NgTWjTn--py3.13/lib/python3.13/site-packages/google/genai/_extra_utils.py", line 310, in invoke_function_from_dict_args
# Jan 11 17:55:35 pitxu poetry[4847]:     return function_to_invoke(**converted_args)
# Jan 11 17:55:35 pitxu poetry[4847]:   File "/home/xavier/pitxu/pitxu/lib/command/system/power_management.py", line 27, in get_battery_level
# Jan 11 17:55:35 pitxu poetry[4847]:     voltage, capacity = self.ups.read_voltage_and_capacity()
# Jan 11 17:55:35 pitxu poetry[4847]:                         ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^
# Jan 11 17:55:35 pitxu poetry[4847]:   File "/home/xavier/pitxu/pitxu/lib/ups/ups.py", line 37, in read_voltage_and_capacity
# Jan 11 17:55:35 pitxu poetry[4847]:     voltage_read = self.bus.read_word_data(address, 2) # 0x02 w
# Jan 11 17:55:35 pitxu poetry[4847]:   File "/home/xavier/.cache/pypoetry/virtualenvs/pitxu-NgTWjTn--py3.13/lib/python3.13/site-packages/smbus2/smbus2.py", line 476, in read_word_data
# Jan 11 17:55:35 pitxu poetry[4847]:     ioctl(self.fd, I2C_SMBUS, msg)
# Jan 11 17:55:35 pitxu poetry[4847]:     ~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^
# Jan 11 17:55:35 pitxu poetry[4847]: OSError: [Errno 121] Remote I/O error