import time

from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi

class SystemDate(PyXavi):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

    format = "%Y-%m-%d"

    def get_current_date(self) -> str:
        '''
        Gets the current system date
        
        Returns:
            The current date in YYYY-MM-DD format
        '''
        return time.strftime(self.format, time.localtime())