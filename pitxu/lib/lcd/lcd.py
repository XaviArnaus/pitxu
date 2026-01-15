import logging, time
from PIL import Image

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.lcd.device_wrapper import DeviceWrapper
from pitxu.lib.canvas.canvas import Canvas
from pitxu.lib.canvas.macros import Macros
from pitxu.lib.objects.point import Point
from pitxu.lib.objects import XprocAction
from definitions import SHARED_LCD_BUSY, SHARED_MATRIX_BUSY, SHARED_SPEAKER_BUSY, SHARED_CHATBOT_BUSY, SHARED_CHATBOT_ANSWER_IS_ERROR,\
    SHARED_LCD_IDLE_MODE

class Lcd(Xprocess):
    '''
    Class to control the behaviour of the LCD display inside a sub-process (child)
    '''

    device: DeviceWrapper = None
    canvas: Canvas = None
    macros: Macros = None
    _display_size: Point = None

    _can_show_kitt_mouth: bool = True

    IDLE_EYES_CADENCE_SECONDS: float = 10.0
    IDLE_EYES_BLINK_DURATION_SECONDS: float = 0.01

    def get_process_name(self) -> str:
        return "LCD"

    def initialize(self):
        self._xlog.info("Initializing LCD Worker")
        # The given device. It handles the interaction with the actual hardware or the mocking.
        self.device = DeviceWrapper(config=self._xconfig, params=self._xparams)
        self._xparams.set("device", self.device)
        # The canvas to draw on
        self.canvas = Canvas(config=self._xconfig, params=self._xparams)
        self._xparams.set("canvas", self.canvas)
        # The macros to do higher level operations, require the device and the canvas via the Xparams
        self._macros = Macros(config=self._xconfig, params=self._xparams)
        # Just have the display size handy
        self._display_size = Point(self._xconfig.get("lcd.size.x"), self._xconfig.get("lcd.size.y"))
        # Initialize the macros statics
        # Commented out until we decide how to merge the eInk and Matrix macros into LCD.
        # self._macros.load_or_create_statics()

    def finish(self):
        self._xlog.info("Finalizing LCD Worker")

    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        # We're busy
        self.set_lcd_busy()

        # ---------- eInk-like actions ----------

        if action == XprocAction.SHOW and param != "":
            self.show(param)
        
        if action == XprocAction.SHOW_IMAGE_EINK and param:
            # Here, param is expected to be an instance of ImageDraw
            self.show_arbitrary_image_while_speaking(param)
        
        if action == XprocAction.SHOW_TALKING_ARBITRARY_EINK and param:
            self.show_arbitrary_text_while_speaking(param)
        
        if action == XprocAction.SHOW_ARBITRARY_TEXT_EINK and param:
            self.show_arbitrary_text_on_lcd(param)

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

        # ---------- matrix-led-like actions ----------

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
            percentage = int(param)
            self._xlog.info(f"🚥 Showing interaction holding percentage {percentage}% on LCD")
            # self._macros.open_canvas()
            self._macros.show_interaction_holding_percentage(percentage)
            # self._macros.close_canvas()
        
        # Clears the screen
        if action == XprocAction.CLEAR or action == XprocAction.LED_CLEAR:
            self.clear()
        
        if action == XprocAction.INIT_STEP and param != "":
            step = int(param)
            # For now, just show the step number as a message
            self.init_step(step)
        
        # Now we're not
        self.unset_lcd_busy()
    
    # ------- eInk-like functions ---------

    def show(self, text: str):
        # Draw the text bubble
        self._xlog.info(f"👀 Showing text bubble on LCD.")
        self._macros.draw_text_bubble(text=text, font=self.canvas.FONT_MEDIUM)
    
    def show_arbitrary_image_while_speaking(self, image_bytes: dict):
        # Show a given image on the LCD display
        self._xlog.info(f"👀 Showing arbitrary image on LCD while speaking.")
        image = Image.frombytes(
            # self._display.get_image().mode,
            # self._display.get_image().size,
            image_bytes["mode"],
            image_bytes["size"],
            bytes.fromhex(image_bytes["image_data"]),
            "raw"
        )
        self.device.display(image, partial=False)
        while self.is_speaker_busy():
            time.sleep(0.01)
        time.sleep(1)  # small delay to ensure the user sees the image
    
    def show_arbitrary_text_while_speaking(self, param: dict):
        self._xlog.info(f"👀 Showing arbitrary text on LCD while speaking.")
        self.show_arbitrary_text_on_lcd(param=param)
        while self.is_speaker_busy():
            time.sleep(0.01)
        time.sleep(1)  # small delay to ensure the user sees the image
    
    def show_arbitrary_text_on_lcd(self, param: dict):
        self._xlog.info(f"👀 Showing arbitrary text on LCD while speaking.")
        self._macros.arbitrary_text_with_icon(
            text=param.get("text", None),
            icon=param.get("icon", None),
            font_size=param.get("font_size", self.canvas.FONT_SIZE_BIG),
            header=param.get("header", None),
            font_header_size=param.get("font_header_size", self.canvas.FONT_SIZE_HUGE),
            padding=param.get("padding", None))

    def splash_ready(self):
        # Draw the ready splash screen
        self._xlog.info(f"👀 Showing ready splash screen on LCD.")
        self._macros.eyes_open()

    def idle(self):
        # Draw the idle screen
        self._xlog.info(f"👀 Showing idle screen on LCD.")

        # Start with a soft clear
        self._macros.soft_clear()

        # It repeats until the speaker is busy
        should_stop_idle = False
        while not should_stop_idle and self.is_lcd_idle_mode():
            # reset the counters and flags
            seconds_waited = 0
            are_eyes_open = False
            # Repeat during the cadence time
            while self.IDLE_EYES_CADENCE_SECONDS > seconds_waited:

                # wait one second
                if are_eyes_open:
                    time.sleep(1)
                    seconds_waited += 1

                # quit if the idle mode is unset from outside
                #   (because we also use the flag in the other direction)
                if not self.is_lcd_idle_mode():
                    self._log_debug(f"Received a idle mode cancel (idle is now [{self.is_lcd_idle_mode()}]).")
                    should_stop_idle = True
                    break
                # show eyes open if not already shown
                if not are_eyes_open:
                    self._macros.eyes_open()
                    are_eyes_open = True

            # We're here because the cadence time is over or because we should stop idle.
            if not should_stop_idle:
                # show the eyes closed
                self._macros.eyes_closed()
                # and wait a bit
                time.sleep(self.IDLE_EYES_BLINK_DURATION_SECONDS)

    def splash_startup(self):
        # Draw the startup splash screen
        self._xlog.info(f"👀 Showing startup splash screen on eInk.")
        self._macros.startup_splash()
    
    # ------- Common functions ---------
    
    def clear(self):
        # Clear the display
        self.device.clear()
    
    def soft_clear(self):
        # Clear the display using a white rectangle as a partial
        self._macros.soft_clear()

    # ------- Matrix-LED-like functions ---------
    
    def show_kitt_mouth_while_speaking(self):
        self._xlog.info(f"👄 Showing KITT mouth on Matrix LED.")
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
    
    def show_kitt_scanner_while_thinking(self):
        self._xlog.info(f"🤖 Showing KITT thinking on Matrix LED.")
        # self._macros.open_canvas()
        while True:
            if not self.is_chatbot_busy():
                self._xlog.info(f"🤖 Stopping KITT thinking on Matrix LED.")
                break
            self._macros.kitt_horizontal_effect()
        # self._macros.close_canvas()
    
    def show(self, text: str):
        self._xlog.info(f"🚥 Drawing on Matrix LED: {text}")
        self._macros.draw_something()
    
    def init_step(self, step: int):
        self._xlog.info(f"🚥 Showing init step {step} on Matrix LED")
        # For now, just show the step number as a message
        self._macros.show_init_step(step)

    # ------- Communication with Flags ---------

    # KITT mouth control: is it allowed or are we doing something else?
    def is_kitt_mouth_allowed(self):
        return self._can_show_kitt_mouth
    
    # KITT mouth control: internally, even allowed, we only show it when the speaker is busy.
    def is_speaker_busy(self):
        return self.read_shared_memory_flag(SHARED_SPEAKER_BUSY)
    
    def is_chatbot_busy(self):
        return self.read_shared_memory_flag(SHARED_CHATBOT_BUSY)

    # LCD busy control: is it already busy?
    def is_lcd_busy(self):
        # return self.read_shared_memory_flag(SHARED_LCD_BUSY)
        return self.read_shared_memory_flag(SHARED_MATRIX_BUSY)
    
    # LCD busy control: set as busy
    def set_lcd_busy(self):
        # self.write_shared_memory_flag(SHARED_LCD_BUSY, True)
        self.write_shared_memory_flag(SHARED_MATRIX_BUSY, True)

    # LCD busy control: unset as busy
    def unset_lcd_busy(self):
        # self.write_shared_memory_flag(SHARED_LCD_BUSY, False)
        self.write_shared_memory_flag(SHARED_MATRIX_BUSY, False)

    # LCD idle mode control: is it in idle mode?
    def is_lcd_idle_mode(self):
        return self.read_shared_memory_flag(SHARED_LCD_IDLE_MODE)
