from multiprocessing import Queue, Process

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary

import logging

# It is not used by now
class ProcessPool:

    _processes: dict
    _queue: Queue

    _config: Config = None
    _logger: logging = None
    _parameters: Dictionary = None

    def __init__(self, config: Config, params: Dictionary):
        self._parameters = params
        self._config = config
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()
        self._queue = Queue()
        self._processes = {}

    def add(self, name: str, process: Process):
        self._logger.debug("Adding process [" + name + "] to the pool")
        if name in self._processes:
            self._logger.warning("Process [" + name + "] already exists in the pool. Overwriting.")
        self._processes[name] = process
    
    def new(self, name: str, target):
        self._logger.debug("Creating and adding process [" + name + "] to the pool")
        if name in self._processes:
            self._logger.warning("Process [" + name + "] already exists in the pool. Overwriting.")
        self._processes[name] = Process(target=target, args=(self._config, self._parameters, self._queue,))
    
    def get(self, name: str):
        if name in self._processes:
            return self._processes[name]
        else:
            self._logger.error("Process [" + name + "] does not exist in the pool.")
            return None
    
    def remove(self, name: str):
        if name in self._processes:
            self._logger.debug("Removing process [" + name + "] from the pool")
            del self._processes[name]
        else:
            self._logger.error("Process [" + name + "] does not exist in the pool.")
    
    def broadcast(self, message):
        self._queue.put((message))
        
