import logging

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction

class XprocessDisplayBackground(Xprocess):
    '''
    Class to define the protocol for Display background processes.
    '''

    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        # We're busy
        self.set_busy()

        # ---------- background interaction actions ----------

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
        
        if action == XprocAction.INIT_STEP and param != "":
            step = int(param)
            # For now, just show the step number as a message
            self.init_step(step)
        
        # Now we're not
        self.unset_busy()
    
    # ------- Common functions ---------
    
    def clear(self):
        raise NotImplementedError("clear() must be implemented in Display Background subclasses.")
    
    def soft_clear(self):
        raise NotImplementedError("soft_clear() must be implemented in Display Background subclasses.")
    
    def get_canvas_handler(self):
        raise NotImplementedError("get_canvas_handler() must be implemented in Display Background subclasses.")

    # ------- Background Interaction functions ---------
    
    def show_kitt_mouth_while_speaking(self):
        raise NotImplementedError("show_kitt_mouth_while_speaking() must be implemented in Display Background subclasses.")
    
    def show_kitt_scanner_while_thinking(self):
        raise NotImplementedError("show_kitt_scanner_while_thinking() must be implemented in Display Background subclasses.")

    def show(self, text: str):
        raise NotImplementedError("show() must be implemented in Display Background subclasses.")

    def init_step(self, step: int):
        raise NotImplementedError("init_step() must be implemented in Display Background subclasses.")
    
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
