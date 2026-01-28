import logging

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction

class XprocessDisplayForeground(Xprocess):
    '''
    Class to define the protocol for Display foreground processes.
    '''

    VERBOSE_DEBUG: bool = False

    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        # We're busy
        self._log_debug("XprocessDisplayForeground: Starting to process action, setting busy status.")
        self.set_busy()

        self._run_foreground_interaction(config, logger, action, param)

         # Now we're not
        self._log_debug("XprocessDisplayForeground: Finished processing action, unsetting busy status.")
        self.unset_busy()

    def _run_foreground_interaction(self, config: Config, logger: logging, action: XprocAction, param: any):
        
        # Shows the message received
        if action == XprocAction.SHOW and param != "":
            self.show(param)
        
        if action == XprocAction.SHOW_IMAGE_EINK and param:
            # Here, param is expected to be an instance of ImageDraw
            self.show_arbitrary_image_while_speaking(param)
        
        if action == XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND_TALKING and param:
            self.show_arbitrary_text_while_speaking(param)
        
        if action == XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND and param:
            self.show_arbitrary_text_on_foreground(param)

        # Shows the Idle splash screen
        if action == XprocAction.SHOW_IDLE:
            self.idle()

        # Shows the Ready splash screen
        if action == XprocAction.READY:
            self.splash_ready()
        
        # Shows the Startup splash screen
        if action == XprocAction.STARTUP:
            if param is None or param == "":
                self.splash_startup()
            else:
                self.splash_startup(for_seconds=float(param))
        
        # Clears the screen
        if action == XprocAction.CLEAR or action == XprocAction.EINK_CLEAR:
            self.clear()
        
        # Clears the foreground screen only
        if action == XprocAction.EINK_CLEAR or action == XprocAction.FOREGROUND_CLEAR:
            self.clear_foreground()
        
        # Clears the screen using a partial white
        if action == XprocAction.SOFT_CLEAR:
            self.soft_clear()
    
    # ------- Common functions ---------
    
    def clear(self):
        raise NotImplementedError("clear() must be implemented in Display Background subclasses.")
    
    def soft_clear(self):
        raise NotImplementedError("soft_clear() must be implemented in Display Background subclasses.")
    
    # This is supposed to be the new clear for foreground only
    def clear_foreground(self):
        raise NotImplementedError("clear_foreground() must be implemented in Display Foreground subclasses.")

    def get_canvas_handler(self):
        raise NotImplementedError("get_canvas_handler() must be implemented in Display Background subclasses.")

    # ------- Foreground Interaction functions ---------
    
    def show(self, text: str):
        raise NotImplementedError("show() must be implemented in Display Background subclasses.")
    
    def show_arbitrary_image_while_speaking(self, image_bytes: dict):
        raise NotImplementedError("show_arbitrary_image_while_speaking() must be implemented in Display Background subclasses.")

    def show_arbitrary_text_while_speaking(self, param: dict):
        raise NotImplementedError("show_arbitrary_text_while_speaking() must be implemented in Display Background subclasses.")
    
    def show_arbitrary_text_on_foreground(self, param: dict):
        raise NotImplementedError("show_arbitrary_text_on_foreground() must be implemented in Display Background subclasses.")

    def splash_ready(self):
        raise NotImplementedError("splash_ready() must be implemented in Display Background subclasses.")

    def idle(self):
        raise NotImplementedError("idle() must be implemented in Display Background subclasses.")

    def splash_startup(self, for_seconds: float = 3.0):
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
