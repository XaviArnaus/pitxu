from pyxavi import Logger
import logging
from logging import NOTSET
import multiprocessing_logging

from pyxavi import TerminalColor

class XLogger(logging.Logger, Logger):
    '''
    Extended Logger class for PyXavi, with additional utility methods.
    '''

    adapters: list[logging.LoggerAdapter] = []
    __using_old_config = False

    def __init__(self, name, level=NOTSET):
        super().__init__(name, level)
        self.adapters = []

    def add_adapter(self, adapter):
        self.adapters.append(adapter)
    
    def initialize(self, config=None, base_path=""):
        self._base_path = base_path
        self._load_config(config=config)

        # Setting up the handlers straight away
        self._clean_handlers()
        self._set_handlers()

        # Define basic configuration
        logging.basicConfig(
            # Define logging level
            level=self._logger_config.get("loglevel"),
            # Define the format of log messages
            format=self._logger_config.get("format"),
            # Declare handlers
            handlers=self._handlers
        )

        # Define your own logger name
        self._logger = logging.getLogger(self._logger_config.get("name"))

        # Make it available for multiprocessing
        if self._logger_config.get("stdout.multiprocess"):
            multiprocessing_logging.install_mp_handler(logger=self._logger)

        # In case we are using the old config, show a warning
        if self.__using_old_config:
            self._logger.warning(
                f"{TerminalColor.YELLOW_BRIGHT}[pyxavi] " +
                "An old version of the configuration file structure for " +
                "the Logger module has been loaded. This is deprecated.\n" +
                "Please migrate your configuration file to the new structure.\n" +
                "Read https://github.com/XaviArnaus/pyxavi/blob/main/docs/logger.md" +
                f"{TerminalColor.END}"
            )

    def _log(self, level, msg, args, **kwargs):
        if "extra" not in kwargs:
            kwargs["extra"] = {}
        kwargs["extra"]["className"] = self.__class__.__name__

        for adapter in self.adapters:
            msg, kwargs = adapter.process(msg, kwargs)

        super()._log(level, msg, args, **kwargs)
