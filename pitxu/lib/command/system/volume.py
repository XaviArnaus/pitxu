from pyxavi import Config, Dictionary, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.canvas.canvas import Canvas

import logging, platform

from subprocess import check_output


class SystemVolume(PyXavi, Command):

    MUTED = "muted"
    UNMUTED = "unmuted"

    # Whatever the volume we want, we add this to avoid being too low
    SINK_VOLUME_ADDITION = 50

    ALSA_SPEAKER_CONTROL_NAME: str = "Speaker"
    ALSA_MIC_CONTROL_NAME: str = "Mic"

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

        self.SINK_VOLUME_ADDITION = int(self._xconfig.get("text-to-speech.add_to_output_volume", 50))
        self.ALSA_SPEAKER_CONTROL_NAME = self._xconfig.get("text-to-speech.alsa_speaker_control_name", self.ALSA_SPEAKER_CONTROL_NAME)
        self.ALSA_MIC_CONTROL_NAME = self._xconfig.get("text-to-speech.alsa_mic_control_name", self.ALSA_MIC_CONTROL_NAME)

        # This class gets loaded at ChatbotSessionManager initialization time.
        # Therefore, tecnically we can also introduce here any initialization code if needed.
        # We want to set up the microphone volume to a known level: 100
        self.set_local_system_microphone_volume_level(100)

    def get_local_system_speaker_volume_level(self) -> int:
        '''
        Get the local system speaker volume level.

        Returns:
            int: The local system speaker volume level as a percentage (0-100)
        '''
        try:
            if not self._is_linux():
                self._xlog.warning("Getting speaker volume level is only supported on Linux with ALSA. Ignoring.")
                return -1
            self._log_debug("Getting local system speaker volume level using ALSA.")
            call_output = check_output("amixer sget " + self.ALSA_SPEAKER_CONTROL_NAME + " | awk -F'[][]' '/Left:/ { print $2 }'", shell=True).decode()
            #40%
            volume = int(call_output.replace("%", "").strip()) - self.SINK_VOLUME_ADDITION
            if volume < 0:
                volume = 0
            self._log_debug(f"The local system speaker volume level using ALSA is: {volume}%")
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
            if not self._is_linux():
                self._xlog.warning("Getting speaker mute status is only supported on Linux with ALSA. Ignoring.")
                return -1
            self._log_debug("Getting local system speaker mute status using ALSA.")
            call_output = check_output("amixer sget " + self.ALSA_SPEAKER_CONTROL_NAME + " | awk -F'[][]' '/Left:/ { print $6 }'", shell=True).decode()
            #on
            is_muted_str = call_output.strip()
            self._log_debug(f"The local system speaker mute status using ALSA is: {is_muted_str}")
            return is_muted_str.lower() != "on"
        except Exception as e:
            self._xlog.error(f"🛑 Error getting speaker mute status: {e}")
            return False
    
    def set_local_system_speaker_volume_level(self, volume: int) -> int:
        '''
        Set the local system speaker volume level.

        Args:
            volume (int): The desired volume level as a percentage (0-100)
        Returns:
            int: The new volume level as a percentage (0-100)
        '''
        try:
            if not self._is_linux():
                self._xlog.warning("Setting speaker volume level is only supported on Linux with ALSA. Ignoring.")
                return -1
            self._log_debug("Setting local system speaker volume level using ALSA to " + str(volume) + "%.")
            # Unless we want to set volume to 0, we add the addition
            if volume != 0:
                volume += self.SINK_VOLUME_ADDITION
            check_output(f"amixer set {self.ALSA_SPEAKER_CONTROL_NAME} {volume}%", shell=True)
            return self.get_local_system_speaker_volume_level()
        except Exception as e:
            self._xlog.error(f"🛑 Error setting speaker volume level: {e}")
            return -1

    def set_local_system_speaker_mute_status(self, mute: bool) -> str:
        '''
        Set the local system speaker mute status.

        Args:
            mute (bool): True to mute the system, False to unmute
        Returns:
            str: "muted" if the system is muted, "unmuted" otherwise
        '''
        try:
            if not self._is_linux():
                self._xlog.warning("Setting speaker mute status is only supported on Linux with ALSA. Ignoring.")
                return -1
            self._log_debug("Setting local system speaker mute status using ALSA to " + ("MUTED" if mute else "UNMUTED") + ".")
            mute_str = "mute" if mute else "unmute"
            check_output(f"amixer set {self.ALSA_SPEAKER_CONTROL_NAME} {mute_str}", shell=True)
            return self.MUTED if self.get_local_system_speaker_mute_status() else self.UNMUTED
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
            if not self._is_linux():
                self._xlog.warning("Getting microphone volume level is only supported on Linux with ALSA. Ignoring.")
                return -1
            self._log_debug("Getting local system microphone volume level using ALSA.")
            #This works on Pitxu3 (mono mic)
            #call_output = check_output("amixer sget " + self.ALSA_MIC_CONTROL_NAME + " | awk -F'[][]' '/Mono:/ { print $2 }'", shell=True).decode()
            #This works on Pitxu4 (stereo mic)
            call_output = check_output("amixer sget " + self.ALSA_MIC_CONTROL_NAME + " | awk -F'[][]' '/Left:/ { print $2 }'", shell=True).decode()
            #12%
            mic_volume = int(call_output.replace("%", "").strip())
            if mic_volume < 0:
                mic_volume = 0
            self._log_debug(f"The local system microphone volume level using ALSA is: {mic_volume}%")
            return mic_volume
        except Exception as e:
            self._xlog.error(f"Error getting the microphone volume level: {e}")
            return -1
    
    def get_local_system_microphone_mute_status(self) -> bool:
        '''
        Get the local system microphone mute status.

        Returns:
            bool: True if the local system microphone is muted, False otherwise
        '''
        try:
            if not self._is_linux():
                self._xlog.warning("Getting microphone mute status is only supported on Linux with ALSA. Ignoring.")
                return False
            self._log_debug("Getting local system microphone mute status using ALSA.")
            call_output = check_output("amixer sget " + self.ALSA_MIC_CONTROL_NAME + " | awk -F'[][]' '/Mono:/ { print $6 }'", shell=True).decode()
            #Mute: on
            is_muted_str = call_output.split(":")[1].strip()
            self._log_debug(f"The local system microphone mute status using ALSA is: {is_muted_str}")
            return is_muted_str.lower() != "on"
        except Exception as e:
            self._xlog.error(f"Error getting the microphone mute status: {e}")
            return False

    def set_local_system_microphone_volume_level(self, volume: int) -> int:
        '''
        Set the local system microphone volume level.

        Args:
            volume (int): The desired volume level as a percentage (0-100)
        Returns:
            int: The new volume level as a percentage (0-100)
        '''
        try:
            if not self._is_linux():
                self._xlog.warning("Setting microphone volume level is only supported on Linux with ALSA. Ignoring.")
                return -1
            self._xlog.debug(f"Setting local system microphone volume level using ALSA to {volume}%.")
            check_output(f"amixer set {self.ALSA_MIC_CONTROL_NAME} {volume}%", shell=True)
            return self.get_local_system_microphone_volume_level()
        except Exception as e:
            self._xlog.error(f"Error setting the microphone volume level: {e}")
            self._xlog.debug(full_stack())
            return -1

    def set_local_system_microphone_mute_status(self, mute: bool) -> str:
        '''
        Set the local system microphone mute status.

        Args:
            mute (bool): True to mute the system, False to unmute
        Returns:
            str: "muted" if the system is muted, "unmuted" otherwise
        '''
        try:
            if not self._is_linux():
                self._xlog.warning("Setting microphone mute status is only supported on Linux with ALSA. Ignoring.")
                return -1
            self._log_debug("Setting local system microphone mute status using ALSA to " + ("MUTED" if mute else "UNMUTED") + ".")
            mute_str = "mute" if mute else "unmute"
            check_output(f"amixer set {self.ALSA_MIC_CONTROL_NAME} {mute_str}", shell=True)
            return self.MUTED if self.get_local_system_microphone_mute_status() else self.UNMUTED
        except Exception as e:
            self._xlog.error(f"Error setting the microphone mute status: {e}")
    
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

    def _is_linux(self) -> bool:
        os = platform.system()        
        if (os.lower() != "linux"):
            self._log_debug("OS is not Linux, ALSA commands will likely fail. Ignoring")
            return False
        return True