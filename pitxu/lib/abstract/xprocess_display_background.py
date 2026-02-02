import logging

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction

class XprocessDisplayBackground(Xprocess):
    '''
    Class to define the protocol for Display background processes.
    '''

    VERBOSE_DEBUG: bool = False

    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        # We're busy
        self._log_debug("XprocessDisplayBackground: Starting to process action, setting busy status.")
        self.set_busy()

        self._run_background_interaction(config, logger, action, param)

        # Now we're not
        self._log_debug("XprocessDisplayBackground: Finished processing action, unsetting busy status.")
        self.unset_busy()

    def _run_background_interaction(self, config: Config, logger: logging, action: XprocAction, param: any):

        # Shows the message received
        if action == XprocAction.LED and param != "":
            self.show(param)
        
        # Show KITT mouth while speaking
        if action == XprocAction.SAY:
            self.show_kitt_mouth_while_speaking()
        
        # Show KITT scanner while thinking
        if action == XprocAction.THINKING:
            self.show_kitt_scanner_while_thinking()
        
        if action == XprocAction.INTERACTION_HOLDING_PERCENTAGE and param != "":
            self.interaction_holding_percentage(int(param))
        
        # Clears the screen
        if action == XprocAction.CLEAR or action == XprocAction.LED_CLEAR:
            self.clear()
        
        # Clears the background screen only
        if action == XprocAction.LED_CLEAR or action == XprocAction.BACKGROUND_CLEAR:
            self._log_debug("XprocessDisplayBackground: Clearing background screen only.")
            self.clear_background()
        
        if action == XprocAction.INIT_STEP and param != "":
            step = int(param)
            # For now, just show the step number as a message
            self.init_phase(step)
    
    # def _initialize_on_every_run(self):
    #     '''
    #     Initializations needed on every run of the process.
    #     Overloading the xprocess's one.
    #     '''
    #     super(XprocessDisplayBackground, self)._initialize_on_every_run()

    #     # Add the interaction delays coming from params
    #     self._xlog.debug("XprocessDisplayBackground: Setting interaction delays from params.")
    #     self.interaction_delays = self._xparams.get("interaction_delays", {})
    
    # ------- Common functions ---------
    
    def clear(self):
        raise NotImplementedError("clear() must be implemented in Display Background subclasses.")
    
    def soft_clear(self):
        raise NotImplementedError("soft_clear() must be implemented in Display Background subclasses.")

    # This is supposed to be the new clear for background only
    def clear_background(self):
        raise NotImplementedError("clear_background() must be implemented in Display Background subclasses.")
    
    def get_canvas_handler(self):
        raise NotImplementedError("get_canvas_handler() must be implemented in Display Background subclasses.")

    # ------- Background Interaction functions ---------
    
    def show_kitt_mouth_while_speaking(self):
        raise NotImplementedError("show_kitt_mouth_while_speaking() must be implemented in Display Background subclasses.")
    
    def show_kitt_scanner_while_thinking(self):
        raise NotImplementedError("show_kitt_scanner_while_thinking() must be implemented in Display Background subclasses.")

    def show(self, text: str):
        raise NotImplementedError("show() must be implemented in Display Background subclasses.")

    def init_phase(self, phase: int):
        raise NotImplementedError("init_phase() must be implemented in Display Background subclasses.")

    def interaction_holding_percentage(self, percentage: int):
        raise NotImplementedError("interaction_holding_percentage() must be implemented in Display Background subclasses.")

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
