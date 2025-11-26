from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

from subprocess import check_output


class SystemVolume(PyXavi):

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