from . import PyXavi
from pyxavi import Config
from pitxu.lib.utils import ConfigLoader
from pitxu.lib.dto import QueueItemType, QueueItemAction

from multiprocessing import Process, Queue
import logging

class Xprocess(PyXavi, Process):

    _queue: Queue = None

    def __init__(self, queue: Queue, *kargs):

        self._queue = queue

        # Calls the PyXavi.__init__(self,whatever,params,we,send)
        super(Xprocess, self).__init__(*kargs)
    
    def run(self):
        '''
        Managed by Process
        Gets called whenever the self._queue.put() is called from the main.py
        '''

        # Apparently the parent Process class has a run() implementation,
        # but I don't see the difference in behaviour.
        super(Xprocess, self).run()

        try:
            # This is needed to have the logging connected:
            # - Create the Config object from scratch
            # - Use the Config object to initialise the Logger. Be sure that the `stdout.multiprocess`
            #       or `file.multiprocess` is True. Each activate their respective multiproces support.
            #       WARNING: Unintentionally, stdout works multiprocess without activating! Bug!
            # - ONLY THEN we will see logging messages in the main logger.
            self._config = ConfigLoader.load_config_files()
            self._init_logger(config=self._config)


            self._logger.debug("Xprocess run()")
            for queue_item in iter(self._queue.get, None):
                type, message = queue_item
                self._logger.debug("Xprocess run() received a [" + type + "]: [" + message + "]")

                # Executes the own do() passing the context.
                if type == QueueItemType.DO:
                    self.do(self._config, self._logger, message)
                
                # Initializes the model from within the Process.
                # This is the only way to avoid Model Session issues
                if type == QueueItemType.ACTION and message == QueueItemAction.INITIALIZE:
                    self.initialize()

                # We don't need to finish the subprocess from main explicitly, it will end when the job
                #   is done or when we call join() from main.
                # Still, we leave it so we have the tool for whatever other reason.
                if type == QueueItemType.ACTION and message == QueueItemAction.FINISH:
                    self.finish()

        except KeyboardInterrupt:
            self._logger.debug("Pressed Control + C while running Xprocess run()")
            self.finish()
    
    def initialize(self):
        '''
        This is called from from __init__() when instantiated (can be avoided) or from 
        outside via QueueItemAction.INITIALIZE to init itself anything, 
        it won't be triggered in every run(). 
        Most likely you want to initiate here the models within the Process, avoiding
        issues with session serialisation (I look at you, PiperSession)
        '''
        super(Xprocess, self).__init__()
    
    def do(self, config: Config, logger: logging):
        '''
        This is what you want to implement in your child class as the actual work.
        Called from run() with the initialised basic framework.
        '''
        pass
    
    def finish(self):
        '''
        This is called from from run() via KeyboardInterrupt or from outside via 
        QueueItemAction.FINISH to finish gracefully whatever we have open.
        Do not try to terminate the process from inside itself.
        '''
        pass
        