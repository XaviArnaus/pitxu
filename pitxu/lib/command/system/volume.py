from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.utils.device_monitor import DeviceMonitor

import logging


class SystemVolume(PyXavi, Command):
    """
    Chatbot tools for the speaker and microphone volumes.

    It does not touch ALSA: everything goes through the DeviceMonitor, that reads and writes the soundcard
    and publishes the values to the shared memory.
    """

    MUTED = "muted"
    UNMUTED = "unmuted"

    UNKNOWN = -1

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

        if self._xparams.key_exists("device_monitor") and self._xparams.get("device_monitor") is not None:
            self._monitor: DeviceMonitor = self._xparams.get("device_monitor")
        else:
            self._xlog.warning("SystemVolume did not receive the shared DeviceMonitor, creating its own.")
            self._monitor = DeviceMonitor(config=self._xconfig, params=self._xparams)

    def get_local_system_speaker_volume_level(self) -> int:
        '''
        Get the local system speaker volume level.

        Returns:
            int: The local system speaker volume level as a percentage (0-100). -1 if it can't be read.
        '''
        volume = self._monitor.get_speaker_volume()
        return self.UNKNOWN if volume is None else volume

    def get_local_system_speaker_mute_status(self) -> bool:
        '''
        Get the local system speaker mute status.

        Returns:
            bool | int: True if the local system speaker is muted, False otherwise, -1 if unknown
        '''
        muted = self._monitor.get_speaker_muted()
        return self.UNKNOWN if muted is None else muted

    def set_local_system_speaker_volume_level(self, volume: int) -> int:
        '''
        Set the local system speaker volume level.

        Args:
            volume (int): The desired volume level as a percentage (0-100)
        Returns:
            int: The new volume level as a percentage (0-100). -1 if it could not be set.
        '''
        new_volume = self._monitor.set_speaker_volume(volume)
        return self.UNKNOWN if new_volume is None else new_volume

    def set_local_system_speaker_mute_status(self, mute: bool) -> str:
        '''
        Set the local system speaker mute status.

        Args:
            mute (bool): True to mute the system, False to unmute
        Returns:
            str: "muted" if the system is muted, "unmuted" otherwise
        Returns -1 if the operation could not be performed.
        '''
        muted = self._monitor.set_speaker_muted(mute)
        if muted is True:
            return self.MUTED
        if muted is False:
            return self.UNMUTED
        # Unknown: this soundcard has no mute switch, so the command had no effect.
        self._xlog.warning("The speaker has no mute switch: could not mute or unmute.")
        return self.UNKNOWN

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
            int: The local system microphone volume level as a percentage (0-100). -1 if it can't be read.
        '''
        volume = self._monitor.get_mic_volume()
        return self.UNKNOWN if volume is None else volume

    def get_local_system_microphone_mute_status(self) -> bool:
        '''
        Get the local system microphone mute status.

        Returns:
            bool: True if the local system microphone is muted, False otherwise
        '''
        return self._monitor.get_mic_muted() is True

    def set_local_system_microphone_volume_level(self, volume: int) -> int:
        '''
        Set the local system microphone volume level.

        Args:
            volume (int): The desired volume level as a percentage (0-100)
        Returns:
            int: The new volume level as a percentage (0-100). -1 if it could not be set.
        '''
        new_volume = self._monitor.set_mic_volume(volume)
        return self.UNKNOWN if new_volume is None else new_volume

    def set_local_system_microphone_mute_status(self, mute: bool) -> str:
        '''
        Set the local system microphone mute status.

        Args:
            mute (bool): True to mute the system, False to unmute
        Returns:
            str: "muted" if the system is muted, "unmuted" otherwise
        '''
        return self.MUTED if self._monitor.set_mic_muted(mute) is True else self.UNMUTED

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
