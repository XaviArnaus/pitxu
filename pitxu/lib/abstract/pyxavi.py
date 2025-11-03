from pyxavi import Logger, Config, Dictionary

import logging

class PyXavi:

    _config: Config = None
    _logger: logging = None
    _parameters: Dictionary = None

    def __init__(self, config: Config, params: Dictionary):
        self._parameters = params
        self._config = config
        # self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()
        self._init_logger()

        if (params.get("init", True)):
            self.initialise()
    
    def _init_logger(self, config: Config = None):
        '''
        Needed to be able to initialise (again) from within the Xprocess.run()
        '''
        config = config if config is not None else self._config
        self._logger = Logger(config=self._config, base_path=self._parameters.get("base_path", "")).get_logger()

    def initialise(self):
        pass