import logging

from pyxavi import Config

from pitxu.lib.abstract.xprocess_display_foreground import XprocessDisplayForeground
from pitxu.lib.abstract.xprocess_display_background import XprocessDisplayBackground
from pitxu.lib.objects import XprocAction

class XprocessDisplayCombined(XprocessDisplayForeground, XprocessDisplayBackground):
    '''
    Class to define the protocol for Display foreground processes.
    '''

    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        # We're busy
        self.set_busy()

        # ---------- foreground interaction actions ----------

        super(XprocessDisplayCombined, self)._run_foreground_interaction(config, logger, action, param)

         # ---------- background interaction actions ----------

        super(XprocessDisplayCombined, self)._run_background_interaction(config, logger, action, param)

        # ---------- common interaction actions ----------
        
        # Clears the screen
        if action == XprocAction.CLEAR:
            self.clear()
        
        # Clears the screen using a partial white
        if action == XprocAction.SOFT_CLEAR:
            self.soft_clear()
        
        # Clears the background screen only
        if action == XprocAction.LED_CLEAR or action == XprocAction.BACKGROUND_CLEAR:
            self.clear_background()
        
        # Clears the foreground screen only
        if action == XprocAction.EINK_CLEAR or action == XprocAction.FOREGROUND_CLEAR:
            self.clear_foreground()
        
        # Now we're not
        self.unset_busy()
    
    
