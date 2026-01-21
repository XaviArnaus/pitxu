from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.canvas.canvas import Canvas

import logging

from subprocess import check_output


class SystemVolume(PyXavi, Command):

    MUTED = "muted"
    UNMUTED = "unmuted"

    # Whatever the volume we want, we add this to avoid being too low
    SINK_VOLUME_ADDITION = 50

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

        self.SINK_VOLUME_ADDITION = int(self._xconfig.get("text-to-speech.add_to_output_volume", 50))

    def get_local_system_speaker_volume_level(self) -> int:
        '''
        Get the local system speaker volume level.

        Returns:
            int: The local system speaker volume level as a percentage (0-100)
        '''
        try:
            call_output = check_output("pactl get-sink-volume @DEFAULT_SINK@", shell=True).decode()
            #Volume: front-left: 78642 / 120% / 4.75 dB,   front-right: 78642 / 120% / 4.75 dB
            #balance 0.00
            volume = int(call_output.split("/")[1].strip().rstrip("%")) - self.SINK_VOLUME_ADDITION
            if volume < 0:
                volume = 0
            return volume
        except Exception as e:
            self._xlog.error(f"Error getting volume level: {e}")
            return -1
    
    def get_local_system_speaker_mute_status(self) -> bool:
        '''
        Get the local system speaker mute status.

        Returns:
            bool: True if the local system speaker is muted, False otherwise
        '''
        try:
            call_output = check_output("pactl get-sink-mute @DEFAULT_SINK@", shell=True).decode()
            #Mute: yes
            is_muted_str = call_output.split(":")[1].strip()
            return is_muted_str.lower() == "yes"
        except Exception as e:
            self._xlog.error(f"Error getting mute status: {e}")
            return False
    
    def set_local_system_speaker_volume_level(self, volume: int) -> int:
        '''
        Set the local system speaker volume level.

        Args:
            volume (int): The desired volume level as a percentage (0-100)
        '''
        try:
            # Unless we want to set volume to 0, we add the addition
            if volume != 0:
                volume += self.SINK_VOLUME_ADDITION
            check_output(f"pactl set-sink-volume @DEFAULT_SINK@ {volume}%", shell=True)
            return volume - self.SINK_VOLUME_ADDITION
        except Exception as e:
            self._xlog.error(f"Error setting volume level: {e}")
            return -1

    def set_local_system_speaker_mute_status(self, mute: bool) -> str:
        '''
        Set the local system speaker mute status.

        Args:
            mute (bool): True to mute the system, False to unmute
        '''
        try:
            mute_str = "1" if mute else "0"
            check_output(f"pactl set-sink-mute @DEFAULT_SINK@ {mute_str}", shell=True)
            return self.MUTED if mute else self.UNMUTED
        except Exception as e:
            self._xlog.error(f"Error setting mute status: {e}")
    
    def callback_volume_level(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_local_system_speaker_volume_level` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_local_system_speaker_volume_level`.

        """
        log.info(f"The volume level in the callback is: {value}")

        try:
            # New approach, using the existing display instance via main
            log.error(f"🔊 Showing volume level on eInk: [{value}]")
            interaction.show_arbitrary_text_on_eink(
                icon="🔊",
                text=f"{value} %",
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing volume level on eInk: {e}")

    def callback_muting(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_local_system_speaker_volume_level` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_local_system_speaker_volume_level`.

        """
        log.info(f"The volume level in the callback is: {value}")

        try:

            # New approach, using the existing display instance via main
            log.error(f"🔊 Showing mute status on eInk: [{value}]")
            interaction.show_arbitrary_text_on_eink(
                icon="🔇" if value == self.MUTED or value == True else "🔈",
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing volume level on eInk: {e}")

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_local_system_speaker_volume_level,
                self.set_local_system_speaker_volume_level,
                self.set_local_system_speaker_mute_status,
                self.get_local_system_speaker_mute_status]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_local_system_speaker_volume_level" or function_name == "set_local_system_speaker_volume_level":
            return self.callback_volume_level
        elif function_name == "set_local_system_speaker_mute_status" or function_name == "get_local_system_speaker_mute_status":
            return self.callback_muting
        return self.default_empty_callback