import logging

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction

class XprocessDisplayButtonsLeft(Xprocess):
    '''
    Class to define the protocol for Display status processes.
    '''

    VERBOSE_DEBUG: bool = False

    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        # We're busy
        self._log_debug("XprocessDisplayButtonsLeft: Starting to process action, setting busy status.")
        self.set_busy()

        self._run_status_interaction(config, logger, action, param)

        # Now we're not
        self._log_debug("XprocessDisplayButtonsLeft: Finished processing action, unsetting busy status.")
        self.unset_busy()

    def _run_status_interaction(self, config: Config, logger: logging, action: XprocAction, param: any):

        # Shows the buttons
        if action == XprocAction.BUTTON_MICROPHONE and param is not None:
            self.show_button_microphone(param)
        if action == XprocAction.BUTTON_CHATBOT and param is not None:
            self.show_button_chatbot(param)
        if action == XprocAction.BUTTON_TRANSCRIPTION and param is not None:
            self.show_button_transcription(param)

        # Clears the screen
        if action == XprocAction.CLEAR:
            self.clear()
        
        # Clears the status screen only
        if action == XprocAction.STATUS_CLEAR or action == XprocAction.SOFT_CLEAR:
            self._log_debug("XprocessDisplayButtonsLeft: Clearing status screen only.")
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

    # ------- Buttons Interaction functions ---------
    
    def show_button_transcription(self, param: dict):
        raise NotImplementedError("show_button_transcription() must be implemented in Display Buttons Left subclasses.")
    
    def show_button_chatbot(self, param: dict):
        raise NotImplementedError("show_button_chatbot() must be implemented in Display Buttons Left subclasses.")
    
    def show_button_microphone(self, param: dict):
        raise NotImplementedError("show_button_microphone() must be implemented in Display Buttons Left subclasses.")

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
