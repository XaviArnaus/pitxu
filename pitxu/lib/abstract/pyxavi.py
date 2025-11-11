from pyxavi import Logger, Config, Dictionary

from multiprocessing import Process
import logging

class PyXavi(Process):

    _config: Config = None
    _logger: logging = None
    _parameters: Dictionary = None

    def __init__(self, config: Config, params: Dictionary, **kwargs):

        # First of all, call the Process __init__
        super(PyXavi, self).__init__()

        # Get the config from args or kwargs
        self._config = config if config else kwargs.get("config", None)
        if self._config is None:
            raise RuntimeError("Config can not be None")
        # Get the params from args or kwargs
        self._parameters = params if params else kwargs.get("params", Dictionary())
        # Initialise the logger
        self._init_logger()

        if (self._parameters.get("init", True)):
            self.initialise()
    
    def _init_logger(self, config: Config = None):
        '''
        Needed to be able to initialise (again) from within the Xprocess.run()
        '''
        config = config if config is not None else self._config
        self._logger = Logger(config=self._config, base_path=self._parameters.get("base_path", "")).get_logger()

    def initialise(self):
        pass