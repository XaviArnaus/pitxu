import time

from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi

class SystemTime(PyXavi):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

    format = "%H:%M"

    def get_current_time(self) -> str:
        '''
        Gets the current system time

        Returns:
            The current time in HH:MM format
        '''
        try:
            return time.strftime(self.format, time.localtime())
        except Exception as e:
            self._xlog.error(f"Error getting current time: {e}")
            return "Error"