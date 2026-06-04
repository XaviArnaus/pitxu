from pyxavi import Logger, Config, Dictionary, dd

from pitxu.lib.utils.config_loader import ConfigLoader

import logging

class PyXavi:

    _xconfig: Config = None
    _xlog: logging = None
    _xparams: Dictionary = None

    # Do we want a very verbose debug logging?
    VERBOSE_DEBUG: bool = False

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
    
    def _init_logger(self, config: Config = None):
        '''
        Needed to be able to initialise (again) from within the Xprocess.run()
        '''
        config = config if config is not None else self._xconfig
        self._xlog = Logger(config=config, base_path=self._xparams.get("base_path", "")).get_logger()

        # Set verbose debug mode
        self.VERBOSE_DEBUG = config.get("logging.verbose_debug", False) if self.VERBOSE_DEBUG is False else self.VERBOSE_DEBUG
    
    def _log_debug(self, message: str):
        if self.VERBOSE_DEBUG:
            self._xlog.debug(message)
    
    def log_summary(self, title: str, lines: list[str | tuple], tuple_separator: str = ": ", log_level: int = None, attend_verbose_debug_flag: bool = False):
        """
        Logs a summary with a title and lines, formatted in a nice way with borders.

        Parameters:
        title (str): The title of the summary.
        lines (list[str | tuple]): The lines to include in the summary.
        tuple_separator (str, optional): The separator to use for tuple lines. Defaults to ": ".
        log_level (int, optional): The logging level. Defaults to None (DEBUG).
        attend_verbose_debug_flag (bool, optional): Whether to attend the VERBOSE_DEBUG flag. If True, the log level will be set to log_level, otherwise the log will be ignored.

        Attention: Does not support emojis. It messes up with the length.
        """

        if attend_verbose_debug_flag and not self.VERBOSE_DEBUG:
            return

        if log_level is None:
            log_level = logging.DEBUG
        
        printing_lines = []

        # Preprocess the body lines
        body_column_0_length = max([len(line[0]) for line in lines if isinstance(line, tuple)], default=0)
        body_lines = []
        for line in lines:
            if isinstance(line, tuple):
                line_str = f"{str(line[0]).ljust(body_column_0_length)}{tuple_separator}{line[1]}"
            else:
                line_str = line
            body_lines.append(line_str)

        # Calculate length.
        all_lines = [title] + body_lines
        all_lines = [len(line) for line in all_lines] # 2 extra spaces and 2 chars for the lines.
        max_length = max(all_lines)

        # Build the printing lines with borders.
        printing_lines.append("-" * (max_length + 4)) # 4 extra chars for the borders.
        printing_lines.append("| " + title.center(max_length) + " |")
        printing_lines.append("-" * (max_length + 4))
        for line in body_lines:
            printing_lines.append("| " + line.ljust(max_length) + " |")
        printing_lines.append("-" * (max_length + 4))
        
        for line in printing_lines:
            self._xlog.log(log_level, line)