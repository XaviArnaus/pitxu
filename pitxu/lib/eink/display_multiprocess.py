from multiprocessing import Process, JoinableQueue, shared_memory
import logging

from pyxavi import Config, Logger, Dictionary

from pitxu.lib.eink import EinkDisplay, Macros
from pitxu.lib.dto.point import Point
from pitxu.lib.dto import QueueItemType, QueueItemAction, QueueItemDisplay
from pitxu.lib.utils import ConfigLoader
from definitions import ROOT_DIR, SHARED_EINK_BUSY

class DisplayMultiprocess(Process):
    '''
    Class to control the behaviour of the eInk display inside a sub-process (child)

    The eInk is pretty slow. We need semaphores and that's why we need the shared memory flags.
    '''

    _parameters: Dictionary = None
    _config: Config = None
    _logger: logging = None

    _display: EinkDisplay = None
    _macros: Macros = None
    _display_size: Point = None

    _queue: JoinableQueue = None
    _shared_memory: shared_memory.ShareableList = None

    DEFAULT_STROKE: int = 1
    COLOR_BLACK: int = 0
    COLOR_WHITE: int = 1

    def __init__(self, config: Config, params: Dictionary, queue: JoinableQueue):

        # Possible runtime parameters
        self._parameters = params

        # Config is mandatory
        if config is None:
            raise RuntimeError("Config can not be None")
        self._config = config

        # Common Logger
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()

        self._queue = queue

        super(DisplayMultiprocess, self).__init__()
        
    
    def initialize(self):
        self._logger.info("Initializing Display Worker")
        self._display = EinkDisplay(config=self._config, params=self._parameters)
        self._macros = Macros(config=self._config, params=self._parameters)
        self._display_size = Point(self._config.get("display.size.x"), self._config.get("display.size.y"))
        self._initialize_shared_memory()

    def _initialize_shared_memory(self):
        self._logger.info("Loading flags from Shared Memory")
        self._shared_memory = shared_memory.ShareableList(name=self._parameters.get("shared_memory_name"))
        if self._shared_memory is None:
            self._logger.error("Shared Memory is None, cannot read 'e-ink is busy' flag")    
    
    def finish(self):
        '''
        This is called from:
        - run() via KeyboardInterrupt
        - from outside via Queue,

        This is NOT called from
        - by the Python framework when terminating a process -> 

        to finish gracefully whatever we have open.
        
        ! Do not try to terminate the process from inside itself.
        '''
        self._logger.debug("Closing eInk display")
        self._display.close()
        self._logger.debug("Done finishing Display Worker")
    
    def run(self):
        '''
        Managed by Process
        Gets called whenever the self._queue.put() is called from the main.py
        '''
        
        try:
            # Apparently the parent Process class has a run() implementation,
            # but I don't see the difference in behaviour.
            super(DisplayMultiprocess, self).run()

            # This is needed to have the logging connected:
            # - Create the Config object from scratch
            # - Use the Config object to initialise the Logger. Be sure that the `stdout.multiprocess`
            #       or `file.multiprocess` is True. Each activate their respective multiproces support.
            #       WARNING: Unintentionally, stdout works multiprocess without activating! Bug!
            # - ONLY THEN we will see logging messages in the main logger.
            self._config = ConfigLoader.load_config_files()
            self._logger = Logger(config=self._config, base_path=self._parameters.get("base_path", "")).get_logger()
            self._initialize_shared_memory()

            if self._shared_memory is None:
                self._logger.error("Shared Memory is None, cannot read 'e-ink is busy' flag")

            self._logger.debug("Display Worker runs")
            for queue_item in iter(self._queue.get, None):
                type, message = queue_item
                self._logger.debug("Display Worker received a [" + type + "]: [" + message + "]")

                # We're busy
                self.set_eink_busy()

                # Shows the message received
                if type == QueueItemType.SHOW and message != "":
                    self.show(message)
                
                # Shows the Ready splash screen
                if type == QueueItemType.DISPLAY and message == QueueItemDisplay.READY:
                    self.splash_ready()
                
                # Shows the Startup splash screen
                if type == QueueItemType.DISPLAY and message == QueueItemDisplay.STARTUP:
                    self.splash_startup()
                
                # Clears the screen
                if type == QueueItemType.DISPLAY and message == QueueItemDisplay.CLEAR:
                    self.clear()
                
                # Clears the screen using a partial white
                if type == QueueItemType.DISPLAY and message == QueueItemDisplay.SOFT_CLEAR:
                    self.soft_clear()
                
                # Now we're not
                self.unset_eink_busy()
                
                # Initializes the model from within the Process.
                if (type == QueueItemType.ACTION or type == QueueItemType.DISPLAY) and message == QueueItemAction.INITIALIZE:
                    self.initialize()

                # We don't need to finish the subprocess from main explicitly, it will end when the job
                #   is done or when we call join() from main.
                # Still, we leave it so we have the tool for whatever other reason.
                if (type == QueueItemType.ACTION or type == QueueItemType.DISPLAY) and message == QueueItemAction.FINISH:
                    self.finish()
                
                # Finally, we mark this task as done
                self._queue.task_done()

        except KeyboardInterrupt:
            self._logger.debug("Pressed Control + C while running Display subprocess")
            self.finish()
    
    def show(self, text: str):
        # Draw the text bubble
        self._macros.draw_text_bubble(display=self._display, text=text, font=self._display.FONT_MEDIUM)
    
    def splash_ready(self):
        # Draw the ready splash screen
        self._macros.ready_splash(display=self._display)
    
    def splash_startup(self):
        # Draw the ready splash screen
        self._macros.startup_splash(display=self._display)
    
    def clear(self):
        # Clear the display
        self._display.clear()
    
    def soft_clear(self):
        # Clear the display using a white rectangle as a partial
        self._macros.soft_clear()

    def is_eink_busy(self):
        # Uses the Shared memory flag to answer.
        return self._shared_memory[SHARED_EINK_BUSY]
    
    def set_eink_busy(self):
        self._shared_memory[SHARED_EINK_BUSY] = True

    def unset_eink_busy(self):
        self._shared_memory[SHARED_EINK_BUSY] = False
