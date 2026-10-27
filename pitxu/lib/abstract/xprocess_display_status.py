import logging

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction

class XprocessDisplayStatus(Xprocess):
    '''
    Class to define the protocol for Display status processes.
    '''

    VERBOSE_DEBUG: bool = False

    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        # We're busy
        self._log_debug("XprocessDisplayStatus: Starting to process action, setting busy status.")
        self.set_busy()

        self._run_status_interaction(config, logger, action, param)

        # Now we're not
        self._log_debug("XprocessDisplayStatus: Finished processing action, unsetting busy status.")
        self.unset_busy()

    def _run_status_interaction(self, config: Config, logger: logging, action: XprocAction, param: any):

        # Shows a status entry
        if action == XprocAction.STATUS_LINE and param is not None:
            self.show_status_line(param)

        # Clears the screen
        if action == XprocAction.CLEAR:
            self.clear()
        
        # Clears the status screen only
        if action == XprocAction.STATUS_CLEAR or action == XprocAction.SOFT_CLEAR:
            self._log_debug("XprocessDisplayStatus: Clearing status screen only.")
            self.clear_status()
        
        # Now see if we need to do any extended action for the given action.
        self.extended_status_run(config, logger, action, param)
    
    def extended_status_run(self, config: Config, logger: logging, action: XprocAction, param: any):
        """
        This is called from _run_status_interaction(), allowing for child classes
        to easily extend the actions they manage without needing to override the whole method.
        """
        pass
    
    # ------- Common functions ---------
    
    def clear(self):
        raise NotImplementedError("clear() must be implemented in Display Status subclasses.")
    
    def soft_clear(self):
        raise NotImplementedError("soft_clear() must be implemented in Display Status subclasses.")

    # This is supposed to be the new clear for background only
    def clear_status(self):
        raise NotImplementedError("clear_status() must be implemented in Display Status subclasses.")
    
    def get_canvas_handler(self):
        raise NotImplementedError("get_canvas_handler() must be implemented in Display Status subclasses.")

    # ------- Status Interaction functions ---------
    
    def show_status_line(self, param: dict):
        raise NotImplementedError("show_status_line() must be implemented in Display Status subclasses.")

    # ------- Communication with Flags ---------

    # Display busy control: is it already busy?
    def is_busy(self):
        # return self.read_shared_memory_flag(SHARED_LCD_BUSY)
        return self.read_shared_memory_flag(self.get_busy_flag())
    
    # Display busy control: set as busy
    def set_busy(self):
        # self.write_shared_memory_flag(SHARED_LCD_BUSY, True)
        self.write_shared_memory_flag(self.get_busy_flag(), True)

    # Display busy control: unset as busy
    def unset_busy(self):
        # self.write_shared_memory_flag(SHARED_LCD_BUSY, False)
        self.write_shared_memory_flag(self.get_busy_flag(), False)
