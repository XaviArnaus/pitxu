from pyxavi import Config, Dictionary, full_stack

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

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

        self.SINK_VOLUME_ADDITION = int(self._xconfig.get("text-to-speech.add_to_output_volume", 50))

        # This class gets loaded at ChatbotSessionManager initialization time.
        # Therefore, tecnically we can also introduce here any initialization code if needed.
        # We want to set up the microphone volume to a known level: internally will place
        # LEFT: 0% and RIGHT: {volume}% 
        # De Facto muting the Left Channel (PiSugar Whisplay HAT issue)
        self.set_local_system_microphone_volume_level(100)

    def get_local_system_speaker_volume_level(self) -> int:
        '''
        Get the local system speaker volume level.

        Returns:
            int: The local system speaker volume level as a percentage (0-100)
        '''
        try:
            self._log_debug("Getting local system speaker volume level using pactl.")
            call_output = check_output("pactl get-sink-volume @DEFAULT_SINK@", shell=True).decode()
            #Volume: front-left: 78642 / 120% / 4.75 dB,   front-right: 78642 / 120% / 4.75 dB
            #balance 0.00
            volume = int(call_output.split("/")[1].strip().rstrip("%")) - self.SINK_VOLUME_ADDITION
            if volume < 0:
                volume = 0
            self._log_debug(f"The local system speaker volume level using pactl is: {volume}%")
            return volume
        except Exception as e:
            self._xlog.error(f"🛑 Error getting speaker volume level: {e}")
            return -1
    
    def get_local_system_speaker_mute_status(self) -> bool:
        '''
        Get the local system speaker mute status.

        Returns:
            bool: True if the local system speaker is muted, False otherwise
        '''
        try:
            self._log_debug("Getting local system speaker mute status using pactl.")
            call_output = check_output("pactl get-sink-mute @DEFAULT_SINK@", shell=True).decode()
            #Mute: yes
            is_muted_str = call_output.split(":")[1].strip()
            self._log_debug(f"The local system speaker mute status using pactl is: {is_muted_str}")
            return is_muted_str.lower() == "yes"
        except Exception as e:
            self._xlog.error(f"🛑 Error getting speaker mute status: {e}")
            return False
    
    def set_local_system_speaker_volume_level(self, volume: int) -> int:
        '''
        Set the local system speaker volume level.

        Args:
            volume (int): The desired volume level as a percentage (0-100)
        '''
        try:
            self._log_debug("Setting local system speaker volume level using pactl to " + str(volume) + "%.")
            # Unless we want to set volume to 0, we add the addition
            if volume != 0:
                volume += self.SINK_VOLUME_ADDITION
            check_output(f"pactl set-sink-volume @DEFAULT_SINK@ {volume}%", shell=True)
            return volume - self.SINK_VOLUME_ADDITION
        except Exception as e:
            self._xlog.error(f"🛑 Error setting speaker volume level: {e}")
            return -1

    def set_local_system_speaker_mute_status(self, mute: bool) -> str:
        '''
        Set the local system speaker mute status.

        Args:
            mute (bool): True to mute the system, False to unmute
        '''
        try:
            self._log_debug("Setting local system speaker mute status using pactl to " + ("MUTED" if mute else "UNMUTED") + ".")
            mute_str = "1" if mute else "0"
            check_output(f"pactl set-sink-mute @DEFAULT_SINK@ {mute_str}", shell=True)
            return self.MUTED if mute else self.UNMUTED
        except Exception as e:
            self._xlog.error(f"🛑 Error setting speaker mute status: {e}")

    def callback_speaker_volume_level(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_local_system_speaker_volume_level` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_local_system_speaker_volume_level`.

        """
        try:
            # New approach, using the existing display instance via main
            log.info(f"🔊 Showing speaker volume level on Foreground display: [{value}]")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="🔊",
                text=f"{value} %",
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing speaker volume level on Foreground display: {e}")

    def callback_speaker_muting(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_local_system_speaker_volume_level` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_local_system_speaker_volume_level`.

        """
        try:

            # New approach, using the existing display instance via main
            log.info(f"🔊 Showing speaker mute status on Foreground display: [{value}]")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="🔇" if value == self.MUTED or value == True else "🔈",
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing speaker mute status on Foreground display: {e}")

    def get_local_system_microphone_volume_level(self) -> int:
        '''
        Get the local system microphone volume level.

        Returns:
            int: The local system microphone volume level as a percentage (0-100)
        '''
        try:
            self._log_debug("Getting local system microphone volume level using pactl.")
            call_output = check_output("pactl get-source-volume @DEFAULT_SOURCE@", shell=True).decode()
            #Volume: front-left: 78642 / 120% / 4.75 dB,   front-right: 78642 / 120% / 4.75 dB
            #balance 0.00
            real_volume_left = int(call_output.split("/")[1].strip().rstrip("%"))
            real_volume_right = int(call_output.split("/")[3].strip().rstrip("%"))
            volume_right = real_volume_right - self.SINK_VOLUME_ADDITION
            volume_left = real_volume_left - self.SINK_VOLUME_ADDITION
            if volume_right < 0:
                volume_right = 0
            self._log_debug(f"The local system microphone volume level using pactl is: L{real_volume_left}%, R{real_volume_right}% (showing RIGHT adjusted: {volume_right}%)")
            return volume_right
        except Exception as e:
            self._xlog.error(f"Error getting microphone volume level: {e}")
            return -1
    
    def get_local_system_microphone_mute_status(self) -> bool:
        '''
        Get the local system microphone mute status.

        Returns:
            bool: True if the local system microphone is muted, False otherwise
        '''
        try:
            self._log_debug("Getting local system microphone mute status using pactl.")
            call_output = check_output("pactl get-source-mute @DEFAULT_SOURCE@", shell=True).decode()
            #Mute: yes
            is_muted_str = call_output.split(":")[1].strip()
            self._log_debug(f"The local system microphone mute status using pactl is: {is_muted_str}")
            return is_muted_str.lower() == "yes"
        except Exception as e:
            self._xlog.error(f"Error getting mute status: {e}")
            return False

    def set_local_system_microphone_volume_level(self, volume: int) -> int:
        '''
        Set the local system microphone volume level.

        Args:
            volume (int): The desired volume level as a percentage (0-100)
        '''
        try:
            left_active = self._xconfig.get('speech-to-text.microphone_channels.left', True)
            right_active = self._xconfig.get('speech-to-text.microphone_channels.right', True)
            self._log_debug(f"Setting local system microphone volume level using pactl to {volume}%." + \
                            f"Left channel: {'ON' if left_active else 'OFF'}," + \
                            f"Right channel: {'ON' if right_active else 'OFF'}.")
            # Unless we want to set volume to 0, we add the addition
            if volume != 0:
                volume += self.SINK_VOLUME_ADDITION
            if left_active and not right_active:
                # Left only
                check_output(f"pactl set-source-volume @DEFAULT_SOURCE@ {0}% {volume}%", shell=True)
            elif not left_active and right_active:
                # Right only
                check_output(f"pactl set-source-volume @DEFAULT_SOURCE@ {volume}% {0}%", shell=True)
            else:
                # Both
                check_output(f"pactl set-source-volume @DEFAULT_SOURCE@ {volume}%", shell=True)
            return volume - self.SINK_VOLUME_ADDITION
        except Exception as e:
            self._xlog.error(f"Error setting volume level: {e}")
            self._xlog.debug(full_stack())
            return -1

    def set_local_system_microphone_mute_status(self, mute: bool) -> str:
        '''
        Set the local system microphone mute status.

        Args:
            mute (bool): True to mute the system, False to unmute
        '''
        try:
            self._log_debug("Getting local system microphone mute status using pactl to " + ("MUTED" if mute else "UNMUTED") + ".")
            mute_str = "1" if mute else "0"
            check_output(f"pactl set-source-mute @DEFAULT_SOURCE@ {mute_str}", shell=True)
            return self.MUTED if mute else self.UNMUTED
        except Exception as e:
            self._xlog.error(f"Error setting mute status: {e}")
    
    def callback_microphone_volume_level(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_local_system_microphone_volume_level` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_local_system_microphone_volume_level`.

        """
        try:
            # New approach, using the existing display instance via main
            log.info(f"🎤 Showing microphone volume level on Foreground display: [{value}]")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="🎤",
                text=f"{value} %",
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing microphone volume level on Foreground display: {e}")

    def callback_microphone_muting(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_local_system_microphone_mute_status` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_local_system_microphone_mute_status`.

        """
        try:

            # New approach, using the existing display instance via main
            log.info(f"🎤 Showing microphone mute status on Foreground display: [{value}]")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="❌" if value == self.MUTED or value == True else "🎤",
                text="Muted" if value == self.MUTED or value == True else "Unmuted",
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing mute status on Foreground display: {e}")

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_local_system_speaker_volume_level,
                self.set_local_system_speaker_volume_level,
                self.set_local_system_speaker_mute_status,
                self.get_local_system_speaker_mute_status,
                self.get_local_system_microphone_volume_level,
                self.set_local_system_microphone_volume_level,
                self.get_local_system_microphone_mute_status,
                self.set_local_system_microphone_mute_status]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_local_system_speaker_volume_level" or function_name == "set_local_system_speaker_volume_level":
            return self.callback_speaker_volume_level
        elif function_name == "set_local_system_speaker_mute_status" or function_name == "get_local_system_speaker_mute_status":
            return self.callback_speaker_muting
        elif function_name == "get_local_system_microphone_volume_level" or function_name == "set_local_system_microphone_volume_level":
            return self.callback_microphone_volume_level
        elif function_name == "set_local_system_microphone_mute_status" or function_name == "get_local_system_microphone_mute_status":
            return self.callback_microphone_muting
        return self.default_empty_callback