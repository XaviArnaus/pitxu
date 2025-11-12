from pyxavi import Logger, Config, Dictionary, dd

from pitxu.lib.utils import ConfigLoader

import logging

class PyXavi:

    _xconfig: Config = None
    _xlog: logging = None
    _xparams: Dictionary = None

    def init_pyxavi(self, config: Config = None, params: Dictionary = None, **kwargs):
        '''
        Initializes the PyXavi context (_xconfig, _xlog, _xparams)

        Because PyXavi can be used both in the main process and in subprocesses,
            we need to be able to initialise it from both contexts.
        As Xprocess inherits from PyXavi and Process, we can't have a __init__() in PyXavi,
            so we have this init_pyxavi() method to be called from the child classes.
        When inheriting from a main thread class, call this from its __init__().
        '''
        # Avoid overwriting config if already initialised
        if self._xconfig is None:
            # Get the config from args or kwargs
            self._xconfig = config if config else kwargs.get("config", ConfigLoader.load_config_files())
        
        # Avoid overwriting params if already initialised
        if self._xparams is None:
            # Get the params from args or kwargs
            self._xparams = params if params else kwargs.get("params", Dictionary())

        # Avoid overwriting logger if already initialised
        if self._xlog is None:
            self._init_logger()

        # Now, if we have config, initialise the logger
        self._init_logger()
        # And if we have params and we received the request to call initialise(), do it
        if (bool(self._xparams.get("run_initialize", False))):
            self.initialise()
    
    def _init_logger(self, config: Config = None):
        '''
        Needed to be able to initialise (again) from within the Xprocess.run()
        '''
        config = config if config is not None else self._xconfig
        self._xlog = Logger(config=config, base_path=self._xparams.get("base_path", "")).get_logger()

    def initialise(self):
        pass