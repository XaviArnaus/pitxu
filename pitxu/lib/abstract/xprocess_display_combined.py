import logging

from pyxavi import Config

from pitxu.lib.abstract.xprocess_display_foreground import XprocessDisplayForeground
from pitxu.lib.abstract.xprocess_display_background import XprocessDisplayBackground
from pitxu.lib.objects import XprocAction

class XprocessDisplayCombined(XprocessDisplayForeground, XprocessDisplayBackground):
    '''
    Class to define the protocol for Display foreground processes.
    '''

    VERBOSE_DEBUG: bool = False

    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        # We're busy
        self._log_debug("XprocessDisplayCombined: Starting to process action, setting busy status.")
        self.set_busy()

        # ---------- foreground interaction actions ----------

        super(XprocessDisplayCombined, self)._run_foreground_interaction(config, logger, action, param)

         # ---------- background interaction actions ----------

        super(XprocessDisplayCombined, self)._run_background_interaction(config, logger, action, param)

        # ---------- common interaction actions ----------
        
        # Now we're not
        self._log_debug("XprocessDisplayCombined: Finished processing action, unsetting busy status.")
        self.unset_busy()
    