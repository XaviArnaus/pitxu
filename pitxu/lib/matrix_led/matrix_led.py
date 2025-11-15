import logging

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.matrix_led import Max7219, Macros
from pitxu.lib.objects.point import Point
from pitxu.lib.objects import XprocAction
from definitions import SHARED_MATRIX_BUSY

class MatrixLed(Xprocess):
    '''
    Class to control the behaviour of the LED Matrix display inside a sub-process (child)
    '''

    _matrix: Max7219 = None
    _macros: Macros = None
    _display_size: Point = None

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
            self.show(param)
        
        # Clears the screen
        if action == XprocAction.CLEAR or action == XprocAction.LED_CLEAR:
            self.clear()
        
        # Now we're not
        self.unset_matrix_busy()
    
    def show(self, text: str):
        self._macros.draw_something()
    
    def clear(self):
        self._matrix.clear()

    def is_matrix_busy(self):
        return self.read_shared_memory_flag(SHARED_MATRIX_BUSY)
    
    def set_matrix_busy(self):
        self.write_shared_memory_flag(SHARED_MATRIX_BUSY, True)

    def unset_matrix_busy(self):
        self.write_shared_memory_flag(SHARED_MATRIX_BUSY, False)
