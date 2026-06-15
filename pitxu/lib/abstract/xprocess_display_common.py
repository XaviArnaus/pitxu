import logging

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction

class XprocessDisplayCommon(Xprocess):
    '''
    Class to define the protocol for Display common processes.
    '''

    VERBOSE_DEBUG: bool = False

    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        # We're busy
        self._log_debug("XprocessDisplayCommon: Starting to process action, setting busy status.")
        self.set_busy()

        self._run_common_interaction(config, logger, action, param)

         # Now we're not
        self._log_debug("XprocessDisplayCommon: Finished processing action, unsetting busy status.")
        self.unset_busy()

    def _run_common_interaction(self, config: Config, logger: logging, action: XprocAction, param: any):
        
        # Clears the screen
        if action == XprocAction.CLEAR:
            self.clear()
        
        # Now see if we need to do any extended action for the given action.
        self.extended_common_run(config, logger, action, param)
    
    def extended_common_run(self, config: Config, logger: logging, action: XprocAction, param: any):
        """
        This is called from _run_common_interaction(), allowing for child classes
        to easily extend the actions they manage without needing to override the whole method.
        """
        pass
    
    # ------- Common functions ---------
    
    def clear(self):
        raise NotImplementedError("clear() must be implemented in Display Background and Foreground subclasses.")
    
    def get_canvas_handler(self):
        raise NotImplementedError("get_canvas_handler() must be implemented in Display Foreground subclasses.")

    # ------- Communication with Flags ---------

    # Display busy control: is it already busy?
    def is_busy(self):
        return self.read_shared_memory_flag(self.get_busy_flag())
    
    # Display busy control: set as busy
    def set_busy(self):
        self.write_shared_memory_flag(self.get_busy_flag(), True)

    # Display busy control: unset as busy
    def unset_busy(self):
        self.write_shared_memory_flag(self.get_busy_flag(), False)
