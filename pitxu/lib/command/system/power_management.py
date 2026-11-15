from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.utils.device_monitor import DeviceMonitor
from pitxu.lib.hardware import DisplayControl

import logging

import math

class SystemPowerManagement(PyXavi, Command):
    """
    Chatbot tools for the power, the temperature and the fans of the device.

    It does not touch the hardware: everything goes through the DeviceMonitor, that reads it
    and publishes the values to the shared memory.
    """

    UNKNOWN = -1

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

        if self._xparams.key_exists("device_monitor") and self._xparams.get("device_monitor") is not None:
            self._monitor: DeviceMonitor = self._xparams.get("device_monitor")
        else:
            self._xlog.warning("SystemPowerManagement did not receive the shared DeviceMonitor, creating its own.")
            self._monitor = DeviceMonitor(config=self._xconfig, params=self._xparams)

    def get_battery_level(self) -> int:
        '''
        Get the current battery level

        Returns:
            int: The current battery level as a percentage. -1 if it can't be read.
        '''
        level = self._monitor.get_battery_level()
        return self.UNKNOWN if level is None else level

    def get_power_consumption(self) -> float:
        '''
        Get the current power consumption in watts.

        Returns:
            float: The current power consumption in watts. -1.0 if it can't be read.
        '''
        watts = self._monitor.get_power_consumption()
        if watts is None:
            return -1.0
        self._xlog.debug(f"⚡️ Current power consumption: {watts:.2f} W")
        return watts

    def callback_get_power_consumption(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_power_consumption` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_power_consumption`.

        """
        try:
            log.info(f"⚡️ Showing power consumption on Foreground display: {value} W")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="⚡️",
                text=f"{value} W",
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing power consumption on Foreground display: {e}")
    
    def get_total_charging_estimation_time(self) -> int:
        '''
        Get the estimated time to full charge in minutes.

        Returns:
            int: The estimated time to full charge in minutes.
        '''
        try:
            reading = self._monitor.get_battery_voltage_and_capacity()
            current = self._monitor.get_cpu_amps()  # Convert mA to A
            if reading is None or current is None:
                self._xlog.warning("⚠️ Could not read the battery or the current, cannot estimate charging time.")
                return -1
            voltage, capacity = reading
            if current <= 0:
                self._xlog.warning("⚠️ Current is zero or negative, cannot estimate charging time.")
                return -1
            remaining_capacity = 100 - capacity
            estimated_time_days = ((remaining_capacity / 100) * (capacity / current)) / 24
            estimated = math.modf(estimated_time_days)
            estimated_days = estimated[1]
            estimated = math.modf(estimated[0] * 24)
            estimated_hours = estimated[1]
            estimated_minutes = estimated[0] * 60
            days_part = f" {int(estimated_days)} days " if estimated_days > 0 else ""
            self._xlog.debug(f"⏳ Estimated time to full charge:{days_part} {int(estimated_hours)} hours {int(estimated_minutes)} minutes (Voltage: {voltage} V, Current: {current:.2f} A)")
            return f"{f'{int(estimated_days)}d ' if estimated_days > 0 else ''}{int(estimated_hours)}h {int(estimated_minutes)}m"
        except Exception as e:
            self._xlog.error(f"🛑 Error getting total charging estimation time: {e}")
            return -1
    
    def callback_get_total_charging_estimation_time(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_total_charging_estimation_time` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_total_charging_estimation_time`.

        """
        try:
            log.info(f"⏳ Showing estimated time to full charge on Foreground display: {value}")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="⏳",
                text=f"{value} to full charge",
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing estimated time to full charge on Foreground display: {e}")

    def is_power_cable_connected(self) -> bool | str:
        '''
        Check if the power cable is connected

        Returns:
            bool | str: True if the power cable is connected, False otherwise, "unknown" if this device can't tell.
        '''
        connected = self._monitor.is_power_cable_connected()
        return "unknown" if connected is None else connected

    def get_system_temperature_and_fan_speed(self) -> dict:
        '''
        Get the current system temperature and fan speed.

        Returns:
            dict: A dictionary with 'temperature' in Celsius and 'fan_speed' in RPM.
        '''
        temperature = self._monitor.get_cpu_temperature()
        fan_speed = self._monitor.get_cpu_fan_rpm()
        case_fans = self._monitor.get_case_fans()
        self._log_debug(f"🌡️ Current system temperature: {temperature} °C, 💨 Fan speed: {fan_speed} RPM")
        return {
            "cpu_temperature": self.UNKNOWN if temperature is None else temperature,
            "cpu_fan_speed": self.UNKNOWN if fan_speed is None else fan_speed,
            "case_fans": case_fans
        }

    def callback_system_temperature_and_fan_speed(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_system_temperature_and_fan_speed` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_system_temperature_and_fan_speed`.

        """
        try:
            temperature = value.get("cpu_temperature", -1)
            fan_speed = value.get("cpu_fan_speed", -1)
            case_fans = value.get("case_fans", {})
            case_fans_text = "\n".join([f"{fan_name}: {speed * 100:.0f}%" for fan_name, speed in case_fans.items()])
            text = f"{temperature} °C\n{fan_speed} RPM\n" + (f"Case fans: \n{case_fans_text}" if case_fans_text else "")
            font_size = interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE

            if temperature == -1 or fan_speed == -1:
                text = "❌ Error reading values"
                font_size = interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG

            case_fans_inline = case_fans_text.replace("\n", ", ")
            log.info(f"🌡️ Showing system temperature and fan speed on Foreground display: {temperature} °C, {fan_speed} RPM, {case_fans_inline}")
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
            if value == "unknown":
                icon = "❓"
                text = "Unknown"
            elif bool(value):
                icon = "🔌"
                text = "Connected"
            else:
                icon = "❌"
                text = "Disconnected"
            # New approach, using the existing display instance via main
            log.info(f"🔌 Showing Power Cable Connected: {value}")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon=icon,
                text=text,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing power cable connected status on eInk: {e}")
    
    def is_screen_on(self) -> bool | str:
        '''
        Check if the DSI backlight is on.

        Returns:
            bool | str: True if the DSI backlight is on, False otherwise, "unknown" if it can't be read.
        '''
        is_on = DisplayControl.backlight_is_on()
        return "unknown" if is_on is None else is_on
    
    def turn_off_screen(self) -> bool | str:
        '''
        Turn off the DSI backlight.

        Returns:
            bool | str: The current status of the screen after the command, True if the DSI backlight is on, False otherwise, "unknown" if it can't be read.
        '''
        DisplayControl.set_backlight(False)
        return self.is_screen_on()
    
    def turn_on_screen(self) -> bool | str:
        '''
        Turn on the DSI backlight.

        Returns:
            bool | str: The current status of the screen after the command, True if the DSI backlight is on, False otherwise, "unknown" if it can't be read.
        '''
        DisplayControl.set_backlight(True)
        return self.is_screen_on()
    
    def callback_is_screen_on(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `is_screen_on` that gets called AFTER chatbot from `main`.

        Args:
            log: The logger instance to log messages.
            interaction: The Interaction instance to interact with the user and display information.
            value: The value returned from the Chatbot AFTER it ran `is_screen_on`.
            args: Additional arguments that may be needed for the callback.

        """
        try:
            state = "Unknown" if value == "unknown" else "On" if value else "Off"
            log.info(f"💡 Showing screen ON/OFF status on Foreground display: {state}")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="💡",
                text=f"Screen is {state}",
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing screen status on Foreground display: {e}")

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
                self.get_system_temperature_and_fan_speed,
                self.get_power_consumption,
                self.get_total_charging_estimation_time,
                self.is_screen_on,
                self.turn_off_screen,
                self.turn_on_screen]

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
        elif function_name == "get_power_consumption":
            return self.callback_get_power_consumption
        elif function_name == "get_total_charging_estimation_time":
            return self.callback_get_total_charging_estimation_time
        elif function_name == "is_screen_on" or function_name == "turn_off_screen" or function_name == "turn_on_screen":
            return self.callback_is_screen_on
        return self.default_empty_callback