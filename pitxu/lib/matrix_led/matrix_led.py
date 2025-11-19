import logging

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.matrix_led import Max7219, Macros
from pitxu.lib.objects.point import Point
from pitxu.lib.objects import XprocAction
from definitions import SHARED_MATRIX_BUSY, SHARED_SPEAKER_BUSY

class MatrixLed(Xprocess):
    '''
    Class to control the behaviour of the LED Matrix display inside a sub-process (child)
    '''

    _matrix: Max7219 = None
    _macros: Macros = None
    _display_size: Point = None

    _can_show_kitt_mouth: bool = True

    def get_process_name(self) -> str:
        return "Matrix"

    def initialize(self):
        self._xlog.info("Initializing Matrix Worker")
        self._matrix = Max7219(config=self._xconfig, params=self._xparams)
        self._xparams.set("matrix_device", self._matrix)
        self._macros = Macros(config=self._xconfig, params=self._xparams)
        self._display_size = Point(self._xconfig.get("matrix_led.size.x"), self._xconfig.get("matrix_led.size.y"))
    
    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: str):
        # We're busy
        self.set_matrix_busy()

        # Shows the message received
        if action == XprocAction.LED and param != "":
            # self.disallow_kitt_mouth()
            self.show(param)
        
        if action == XprocAction.SAY:
            self.show_kitt_mouth_while_speaking()
        
        # Clears the screen
        if action == XprocAction.CLEAR or action == XprocAction.LED_CLEAR:
            # self.disallow_kitt_mouth()
            self.clear()
        
        # By default, show a KITT effect while speaking, only if nothing else requested.
        # if self.is_kitt_mouth_allowed():
        #     self.show_kitt_mouth_while_speaking()
        
        # Allow KITT mouth again for future use
        # self.allow_kitt_mouth()
        
        # Now we're not
        self.unset_matrix_busy()
    
    def show_kitt_mouth_while_speaking(self):
        self._xlog.info(f"👄 Showing KITT mouth on Matrix LED.")
        self._macros.open_canvas()
        while True:
            if not self.is_speaker_busy():
                self._xlog.info(f"👄 Stopping KITT mouth on Matrix LED.")
                break
            self._macros.kitt_speaking_effect()
        self._macros.close_canvas()
    
    def show(self, text: str):
        self._xlog.info(f"🚥 Drawing on Matrix LED: {text}")
        self._macros.draw_something()
    
    def clear(self):
        self._matrix.clear()

    # ------- Communication with Flags ---------

    # KITT mouth control: is it allowed or are we doing something else?
    def is_kitt_mouth_allowed(self):
        return self._can_show_kitt_mouth
    
    # KITT mouth control: allow
    def allow_kitt_mouth(self):
        self._can_show_kitt_mouth = True
    
    # KITT mouth control: disallow
    def disallow_kitt_mouth(self):
        self._can_show_kitt_mouth = False
    
    # KITT mouth control: internally, even allowed, we only show it when the speaker is busy.
    def is_speaker_busy(self):
        return self.read_shared_memory_flag(SHARED_SPEAKER_BUSY)

    # Matrix busy control: is it already busy?
    def is_matrix_busy(self):
        return self.read_shared_memory_flag(SHARED_MATRIX_BUSY)
    
    # Matrix busy control: set as busy
    def set_matrix_busy(self):
        self.write_shared_memory_flag(SHARED_MATRIX_BUSY, True)

    # Matrix busy control: unset as busy
    def unset_matrix_busy(self):
        self.write_shared_memory_flag(SHARED_MATRIX_BUSY, False)
