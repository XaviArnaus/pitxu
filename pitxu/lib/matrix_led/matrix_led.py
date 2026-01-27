from pitxu.lib.abstract.xprocess_display_background import XprocessDisplayBackground
from pitxu.lib.matrix_led import Max7219, Macros, HandableCanvas, HandableEmulatedCanvas
from pitxu.lib.objects.point import Point
from definitions import SHARED_SPEAKER_BUSY, SHARED_CHATBOT_BUSY, SHARED_CHATBOT_ANSWER_IS_ERROR

class MatrixLed(XprocessDisplayBackground):
    '''
    Class to control the behaviour of the LED Matrix display inside a sub-process (child)
    '''

    _matrix: Max7219 = None
    _macros: Macros = None
    _display_size: Point = None

    def get_process_name(self) -> str:
        return "Matrix"

    def get_canvas_handler(self) -> HandableCanvas | HandableEmulatedCanvas | None:
        if self._macros is not None and self._macros._handable_canvas is not None:
            return self._macros._handable_canvas
        return None

    def initialize(self):
        self._xlog.info("Initializing Matrix Worker")
        self._matrix = Max7219(config=self._xconfig, params=self._xparams)
        self._xparams.set("matrix_device", self._matrix)
        self._macros = Macros(config=self._xconfig, params=self._xparams)
        self._display_size = Point(self._xconfig.get("matrix_led.size.x"), self._xconfig.get("matrix_led.size.y"))
    
    def initialize_from_main_process(self):
        self._xlog.info("Initializing Matrix Worker from Main Process")

        # Just have the display size handy
        self._display_size = Point(self._xconfig.get("matrix_led.size.x"), self._xconfig.get("matrix_led.size.y"))
        self._xparams.set("screen_size", self._display_size)
    
    def finish(self):
        self._xlog.info("Closing possible open canvas")
        self._macros.close_canvas()
        self._xlog.info("Finalizing Matrix Worker")
    
    def show_kitt_mouth_while_speaking(self):
        self._xlog.info(f"👄 Showing KITT mouth on Matrix LED.")
        self._macros.open_canvas()
        while True:
            if not self.is_speaker_busy():
                self._xlog.info(f"👄 Stopping KITT mouth on Matrix LED: Speaker not busy")
                break
            
            if self.read_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR):
                self._macros.show_cross()
            else:
                # New way: we use the VU Meter columns to show the mouth
                # col_1_value = self.read_shared_memory_vu_meter_column(SHARED_VU_COL_1)
                # col_2_value = self.read_shared_memory_vu_meter_column(SHARED_VU_COL_2)
                # col_3_value = self.read_shared_memory_vu_meter_column(SHARED_VU_COL_3)
                # col_4_value = self.read_shared_memory_vu_meter_column(SHARED_VU_COL_4)
                col_1_value = 0
                col_2_value = 0
                col_3_value = 2
                col_4_value = 4
                self._macros.kitt_speaking_effect_vu_meter(col_1_value, col_2_value, col_3_value, col_4_value)
        self._macros.close_canvas()
    
    def show_kitt_scanner_while_thinking(self):
        self._xlog.info(f"🤖 Showing KITT thinking on Matrix LED.")
        self._macros.open_canvas()
        while True:
            if not self.is_chatbot_busy():
                self._xlog.info(f"🤖 Stopping KITT thinking on Matrix LED.")
                break
            self._macros.kitt_horizontal_effect()
        self._macros.close_canvas()
    
    def show(self, text: str):
        self._xlog.info(f"🚥 Drawing on Matrix LED: {text}")
        self._macros.draw_something()

    def init_phase(self, phase: int):
        self._xlog.info(f"🚥 Showing init phase {phase} on Matrix LED")
        # For now, just show the phase number as a message
        self._macros.show_init_phase(phase)

    def interaction_holding_percentage(self, percentage: int):
        percentage = int(percentage)
        self._xlog.info(f"🚥 Showing interaction holding percentage {percentage}% on Matrix LED")
        self._macros.show_interaction_holding_percentage(percentage)
    
    def clear(self):
        self._matrix.clear()

    # ------- Communication with Flags ---------

    # KITT mouth control: internally, even allowed, we only show it when the speaker is busy.
    def is_speaker_busy(self):
        return self.read_shared_memory_flag(SHARED_SPEAKER_BUSY)
    
    def is_chatbot_busy(self):
        return self.read_shared_memory_flag(SHARED_CHATBOT_BUSY)

    # # Matrix busy control: is it already busy?
    # REMOVEME: This is now handled in the parent Xprocess
    # def is_matrix_busy(self):
    #     return self.read_shared_memory_flag(SHARED_MATRIX_BUSY)
    
    # # Matrix busy control: set as busy
    # REMOVEME: This is now handled in the parent Xprocess
    # def set_matrix_busy(self):
    #     self.write_shared_memory_flag(SHARED_MATRIX_BUSY, True)

    # # Matrix busy control: unset as busy
    # REMOVEME: This is now handled in the parent Xprocess
    # def unset_matrix_busy(self):
    #     self.write_shared_memory_flag(SHARED_MATRIX_BUSY, False)
