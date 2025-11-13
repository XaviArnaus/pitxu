from typing import Protocol, runtime_checkable
from abc import abstractmethod
import logging

from pyxavi import Config
from pitxu.lib.dto import QueueItemType, QueueItemAction

@runtime_checkable
class XprocessProtocol(Protocol):

    @abstractmethod
    def get_process_name(self) -> str:
        '''
        Return the name of the process.
        '''
        raise NotImplementedError

    def initialize(self) -> None:
        '''
        This is called from outside via QueueItemAction.INITIALIZE to init itself anything, 
        it won't be triggered in every run(). 
        Most likely you want to initiate here the models within the Process, avoiding
        issues with session serialisation (I look at you, PiperSession)
        '''
        pass

    def do(self, config: Config, logger: logging) -> None:
        '''
        This is what you want to implement in your child class as the actual work.
        Called from run() with the initialised basic framework.
        '''
        pass

    @abstractmethod
    def run_with_context(self, config: Config, logger: logging, type: QueueItemType, message: str | QueueItemAction) -> None:
        '''
        This is what you want to implement in your child class as the actual work.
        Called from run() with the initialised basic framework.
        It is meant to be reworked and use do() instead.
        '''
        raise NotImplementedError

    def finish(self) -> None:
        '''
        This is called from:
        - run() via KeyboardInterrupt
        - from outside via Queue,

        This is NOT called from
        - by the Python framework when terminating a process -> 

        to finish gracefully whatever we have open.
        
        ! Do not try to terminate the process from inside itself.
        '''
        pass