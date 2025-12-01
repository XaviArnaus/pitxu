from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command

from subprocess import check_output


class SystemVolume(PyXavi, Command):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

    def get_volume_level(self) -> int:
        '''
        Gets the current system volume level.

        Returns:
            The current volume level as a percentage (0-100)
        '''
        try:
            call_output = check_output("pactl get-sink-volume @DEFAULT_SINK@", shell=True).decode()
            #Volume: front-left: 78642 / 120% / 4.75 dB,   front-right: 78642 / 120% / 4.75 dB
            #balance 0.00
            volume = int(call_output.split("/")[1].strip().rstrip("%"))
            return volume
        except Exception as e:
            self._xlog.error(f"Error getting volume level: {e}")
            return -1
    
    def get_mute_status(self) -> bool:
        '''
        Gets the current mute status of the system.

        Returns:
            True if the system is muted, False otherwise
        '''
        try:
            call_output = check_output("pactl get-sink-mute @DEFAULT_SINK@", shell=True).decode()
            #Mute: yes
            is_muted_str = call_output.split(":")[1].strip()
            return is_muted_str.lower() == "yes"
        except Exception as e:
            self._xlog.error(f"Error getting mute status: {e}")
            return False
    
    def set_volume_level(self, volume: int):
        '''
        Sets the system volume level.

        Args:
            volume: The desired volume level as a percentage (0-100)
        '''
        try:
            check_output(f"pactl set-sink-volume @DEFAULT_SINK@ {volume}%", shell=True)
        except Exception as e:
            self._xlog.error(f"Error setting volume level: {e}")
    
    def set_mute_status(self, mute: bool):
        '''
        Sets the system mute status.

        Args:
            mute: True to mute the system, False to unmute
        '''
        try:
            mute_str = "1" if mute else "0"
            check_output(f"pactl set-sink-mute @DEFAULT_SINK@ {mute_str}", shell=True)
        except Exception as e:
            self._xlog.error(f"Error setting mute status: {e}")
    
    def callback_volume_level(self, main_instance, value) -> None:
        """
        Callback for `get_volume_level` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_volume_level`.

        """
        main_instance._xlog.info(f"The volume level in the callback is: {value}")

        try:
            # Add a percentage sign to the value
            value = f"{value} %"

            # New approach, using the existing display instance via main
            main_instance._xlog.error(f"🔊 Showing volume level on eInk: [{value}]")
            main_instance.show_arbitrary_text_centered_on_eink(value)
        except Exception as e:
            main_instance._xlog.error(f"🛑 Error showing volume level on eInk: {e}")

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_volume_level]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_volume_level":
            return self.callback_volume_level
        return self.default_empty_callback