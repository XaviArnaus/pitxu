import logging

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.eink import EinkDisplay, Macros
from pitxu.lib.objects.point import Point
from pitxu.lib.objects import XprocAction
from definitions import SHARED_EINK_BUSY

class Display(Xprocess):
    '''
    Class to control the behaviour of the eInk display inside a sub-process (child)

    The eInk is pretty slow. We need semaphores and that's why we need the shared memory flags.
    '''

    _display: EinkDisplay = None
    _macros: Macros = None
    _display_size: Point = None

    DEFAULT_STROKE: int = 1
    COLOR_BLACK: int = 0
    COLOR_WHITE: int = 1

    def get_process_name(self) -> str:
        return "Display"

    def initialize(self):
        self._xlog.info("Initializing Display Worker")
        self._display = EinkDisplay(config=self._xconfig, params=self._xparams)
        self._macros = Macros(config=self._xconfig, params=self._xparams)
        self._display_size = Point(self._xconfig.get("display.size.x"), self._xconfig.get("display.size.y"))
    
    def finish(self):
        self._xlog.debug("Closing eInk display")
        self._display.close()
        self._xlog.debug("Done finishing Display Worker")
    
    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: str):
        # We're busy
        self.set_eink_busy()

        # Shows the message received
        if action == XprocAction.SHOW and param != "":
            self.show(param)
        
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
        self.unset_eink_busy()
    
    def show(self, text: str):
        # Draw the text bubble
        self._macros.draw_text_bubble(display=self._display, text=text, font=self._display.FONT_MEDIUM)
    
    def splash_ready(self):
        # Draw the ready splash screen
        self._macros.ready_splash(display=self._display)
    
    def splash_startup(self):
        # Draw the ready splash screen
        self._macros.startup_splash(display=self._display)
    
    def clear(self):
        # Clear the display
        self._display.clear()
    
    def soft_clear(self):
        # Clear the display using a white rectangle as a partial
        self._macros.soft_clear(display=self._display)

    def is_eink_busy(self):
        return self.read_shared_memory_flag(SHARED_EINK_BUSY)
    
    def set_eink_busy(self):
        self.write_shared_memory_flag(SHARED_EINK_BUSY, True)

    def unset_eink_busy(self):
        self.write_shared_memory_flag(SHARED_EINK_BUSY, False)
