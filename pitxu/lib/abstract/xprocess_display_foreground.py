import logging

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction

class XprocessDisplayForeground(Xprocess):
    '''
    Class to define the protocol for Display foreground processes.
    '''

    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        # We're busy
        self.set_busy()

        # ---------- foreground interaction actions ----------

        # Shows the message received
        if action == XprocAction.SHOW and param != "":
            self.show(param)
        
        if action == XprocAction.SHOW_IMAGE_EINK and param:
            # Here, param is expected to be an instance of ImageDraw
            self.show_arbitrary_image_while_speaking(param)
        
        if action == XprocAction.SHOW_TALKING_ARBITRARY_EINK and param:
            self.show_arbitrary_text_while_speaking(param)
        
        if action == XprocAction.SHOW_ARBITRARY_TEXT_EINK and param:
            self.show_arbitrary_text_on_eink(param)

        # Shows the Idle splash screen
        if action == XprocAction.SHOW_IDLE_EINK:
            self.idle()

        # Shows the Ready splash screen
        if action == XprocAction.READY:
            self.splash_ready()
        
        # Shows the Startup splash screen
        if action == XprocAction.STARTUP:
            self.splash_startup()
        
        # Clears the screen
        if action == XprocAction.CLEAR or action == XprocAction.EINK_CLEAR:
            self.clear()
        
        # Clears the screen using a partial white
        if action == XprocAction.SOFT_CLEAR:
            self.soft_clear()
        
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
    
    def show(self, text: str):
        raise NotImplementedError("show() must be implemented in Display Background subclasses.")
    
    def show_arbitrary_image_while_speaking(self, image_bytes: dict):
        raise NotImplementedError("show_arbitrary_image_while_speaking() must be implemented in Display Background subclasses.")

    def show_arbitrary_text_while_speaking(self, param: dict):
        raise NotImplementedError("show_arbitrary_text_while_speaking() must be implemented in Display Background subclasses.")
    
    def show_arbitrary_text_on_eink(self, param: dict):
        raise NotImplementedError("show_arbitrary_text_on_eink() must be implemented in Display Background subclasses.")

    def splash_ready(self):
        raise NotImplementedError("splash_ready() must be implemented in Display Background subclasses.")

    def idle(self):
        raise NotImplementedError("idle() must be implemented in Display Background subclasses.")

    def splash_startup(self):
        raise NotImplementedError("splash_startup() must be implemented in Display Background subclasses.")

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
