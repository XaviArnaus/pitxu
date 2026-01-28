import logging, time
from PIL import Image

from pyxavi import Config

from pitxu.lib.abstract.xprocess_display_combined import XprocessDisplayCombined
from pitxu.lib.lcd.device_wrapper import DeviceWrapper
from pitxu.lib.canvas.canvas import Canvas
from pitxu.lib.canvas.macros import Macros
from pitxu.lib.canvas.painter import Painter
from pitxu.lib.objects.point import Point
from pitxu.lib.interaction.CommConstants import BackgroundComm, ForegroundComm
from pitxu.lib.objects import XprocAction
from definitions import SHARED_LCD_BUSY, SHARED_MATRIX_BUSY, SHARED_SPEAKER_BUSY, SHARED_CHATBOT_BUSY, SHARED_CHATBOT_ANSWER_IS_ERROR,\
    SHARED_LCD_IDLE_MODE

class Lcd(XprocessDisplayCombined):
    '''
    Class to control the behaviour of the LCD display inside a sub-process (child)
    '''

    device: DeviceWrapper = None
    canvas: Canvas = None
    macros: Macros = None
    painter: Painter = None
    _display_size: Point = None

    IDLE_EYES_CADENCE_SECONDS: float = 10.0
    IDLE_EYES_BLINK_DURATION_SECONDS: float = 0.01

    VERBOSE_DEBUG: bool = True

    def get_process_name(self) -> str:
        return "LCD"

    def get_canvas_handler(self) -> Canvas | None:
        if self.canvas is not None:
            return self.canvas
        return None

    def initialize(self):
        self._xlog.info("Initializing LCD Worker")

        # Just have the display size handy
        self._display_size = Point(self._xconfig.get("lcd.size.x"), self._xconfig.get("lcd.size.y"))
        self._xparams.set("screen_size", self._display_size)

        # The given device. It handles the interaction with the actual hardware or the mocking.
        self.device = DeviceWrapper(config=self._xconfig, params=self._xparams)
        self._xparams.set("device", self.device)
        # The canvas to draw on
        self.canvas = Canvas(config=self._xconfig, params=self._xparams)
        self._xparams.set("canvas", self.canvas)
        # The macros to do higher level operations, require the device and the canvas via the Xparams
        self._macros = Macros(config=self._xconfig, params=self._xparams)
        self._xparams.set("macros", self._macros)
        # Initialize the macros statics
        # Commented out until we decide how to merge the eInk and Matrix macros into LCD.
        # self._macros.load_or_create_statics()

        # Add the parent's shared memory manager to the params for the painter
        self._xparams.set("shared_memory", self._shared_memory)

        # The Painter that will handle the actual drawing on the canvas and device
        self.painter = Painter(config=self._xconfig, params=self._xparams)
    
    def initialize_from_main_process(self):
        self._xlog.info("Initializing LCD Worker from Main Process")

        # Just have the display size handy
        self._display_size = Point(self._xconfig.get("lcd.size.x"), self._xconfig.get("lcd.size.y"))
        self._xparams.set("screen_size", self._display_size)

        # The canvas to draw on, but basically to let it be available in the main process
        # and deliver font sizes.
        self.canvas = Canvas(config=self._xconfig, params=self._xparams)
        self._xparams.set("canvas", self.canvas)

    def finish(self):
        self._xlog.info("Finalizing LCD Worker")
        self.painter.close()
        self.canvas.close_canvas()

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
    
    # def show_arbitrary_text_while_speaking(self, param: dict):
    #     self._xlog.info(f"👀 Showing arbitrary text on LCD while speaking.")
    #     self.show_arbitrary_text_on_lcd(param=param)
    #     while self.is_speaker_busy():
    #         time.sleep(0.01)
    #     time.sleep(1)  # small delay to ensure the user sees the image
    
    def show_arbitrary_text_while_speaking(self, param: dict):
        self._xlog.info(f"👀 Showing arbitrary text on LCD while speaking.")

        # self._xlog.debug(f"👀 Waiting for speaker to be busy...")
        # while not self.is_speaker_busy():
        #     time.sleep(0.01)
        # self._xlog.debug(f"👀 Speaker is now busy, showing arbitrary text...")

        # self.painter.set_foreground_interaction(interaction=ForegroundComm.ARBITRARY_TEXT_ICON, parameter=param)
        # self.painter.start_or_resume_paint()

        # What was here originally
        # while self.is_speaker_busy():
        #     time.sleep(0.01)
        
        # Example with lambda, content is irrelevant
        # self.painter.set_busy_flag_callback(SHARED_SPEAKER_BUSY, lambda flag_name, value: self._xlog.debug(f"👀 Speaker busy flag changed to [{value}] while showing arbitrary text."))

        # Setting a callback to close this action when the speaker stops being busy (so finishes speaking)
        # self.painter.set_busy_flag_callback(
        #     flag_name=SHARED_SPEAKER_BUSY,
        #     for_value=False,
        #     callback=self._callback_end_showing_arbitrary_text_while_speaking)
        
        # There can be another way:
        #   - Have a before and after callback, wrapping the painting execution
        #   - The before would wait for the flag to be set to something, in a simply non-blocking if. The loop may be painting the other interaction paint.
        #   - The after would wait for the flag to be set to something else to finish the painting, basically to remove the interaction from the painter.
        #
        #   - This requires 2 sets of callbacks to check per iteration of the painting loop.
        #   - This then allows to have a single painting loop managing multiple interactions with their own lifecycles.
        #   - The downside is that the painting loop becomes more complex and heavier.
        #   - Important to re-emphasize that does not introduce waiting loops, it's every iteration's IF that execute the callback or not.
        #       - This allows the paint thread to keep on running while the other subprocesses are preparing, executing and finishing, freely communicating via busy flags.
        self.painter.paint_into_foreground_while_speaking(
            foreground_interaction=ForegroundComm.ARBITRARY_TEXT_ICON,
            foreground_parameter=param)
        
        # self._log_debug(f"👀 END Showing arbitrary text on LCD while speaking.")

        # self.painter.stop()
        # self.painter.remove_foreground_interaction()
    
    # def _callback_end_showing_arbitrary_text_while_speaking(self):
    #     self._xlog.debug(f"👀 Speaker busy flag changed to  while showing arbitrary text.")
    #     self.painter.stop()
    #     self.painter.remove_foreground_interaction()
    #     # Remove the callback now that we used it
    #     self.painter.remove_busy_flag_callback(flag_name=SHARED_SPEAKER_BUSY, for_value=False)
    #     self._log_debug(f"👀 END Showing arbitrary text on LCD while speaking.")
    
    def show_arbitrary_text_while_thinking(self, param: dict):
        self._xlog.info(f"👀 Showing arbitrary text on LCD while thinking.")

        # while self.is_chatbot_busy():
        #     time.sleep(0.01)

        # self.painter.set_foreground_interaction(interaction=ForegroundComm.ARBITRARY_TEXT_ICON, parameter=param)
        # self.painter.start_or_resume_paint()

        # while self.is_chatbot_busy():
        #     time.sleep(0.01)
        
        # self._log_debug(f"👀 END Showing arbitrary text on LCD while thinking.")

        # self.painter.stop()
        # self.painter.remove_foreground_interaction()
        self.painter.paint_into_foreground_while_thinking(
            foreground_interaction=ForegroundComm.ARBITRARY_TEXT_ICON,
            foreground_parameter=param)

    
    # def show_arbitrary_text_on_lcd(self, param: dict):
    #     self._xlog.info(f"👀 Showing arbitrary text on LCD while speaking.")
    #     self._macros.arbitrary_text_with_icon(
    #         text=param.get("text", None),
    #         icon=param.get("icon", None),
    #         font_size=param.get("font_size", self.canvas.FONT_SIZE_BIG),
    #         header=param.get("header", None),
    #         font_header_size=param.get("font_header_size", self.canvas.FONT_SIZE_HUGE),
    #         padding=param.get("padding", None))
    
    def show_arbitrary_text_on_foreground(self, param: dict):
        self._xlog.info(f"👀 Showing arbitrary text on LCD.")
        for_seconds = param.get("show_for_seconds", Painter.DEFAULT_MAINTAIN_FOREGROUND_PAINT_FOR_SECONDS)
        self.painter.just_paint(
            foreground_interaction=ForegroundComm.ARBITRARY_TEXT_ICON, 
            foreground_parameter=param,
            show_for_seconds=for_seconds)

    def splash_ready(self):
        # Draw the ready splash screen
        self._xlog.info(f"👀 Showing ready splash screen on LCD.")
        self._macros.eyes_open()

    def idle(self):
        pass
        # # Draw the idle screen
        # self._xlog.info(f"👀 Showing idle screen on LCD.")

        # # Start with a soft clear
        # self._macros.soft_clear()

        # # It repeats until the speaker is busy
        # should_stop_idle = False
        # while not should_stop_idle and self.is_lcd_idle_mode():
        #     # reset the counters and flags
        #     seconds_waited = 0
        #     are_eyes_open = False
        #     # Repeat during the cadence time
        #     while self.IDLE_EYES_CADENCE_SECONDS > seconds_waited:

        #         # wait one second
        #         if are_eyes_open:
        #             time.sleep(1)
        #             seconds_waited += 1

        #         # quit if the idle mode is unset from outside
        #         #   (because we also use the flag in the other direction)
        #         if not self.is_lcd_idle_mode():
        #             self._log_debug(f"Received a idle mode cancel (idle is now [{self.is_lcd_idle_mode()}]).")
        #             should_stop_idle = True
        #             break
        #         # show eyes open if not already shown
        #         if not are_eyes_open:
        #             self._macros.eyes_open()
        #             are_eyes_open = True

        #     # We're here because the cadence time is over or because we should stop idle.
        #     if not should_stop_idle:
        #         # show the eyes closed
        #         self._macros.eyes_closed()
        #         # and wait a bit
        #         time.sleep(self.IDLE_EYES_BLINK_DURATION_SECONDS)

    # def splash_startup(self):
    #     # Draw the startup splash screen
    #     self._xlog.info(f"👀 Showing startup splash screen on eInk.")
    #     self._macros.startup_splash()

    def splash_startup(self, for_seconds: float = 3.0):
        # Draw the startup splash screen
        self._xlog.info(f"👀 Showing startup splash screen")
        self.painter.just_paint(foreground_interaction=ForegroundComm.STARTUP, show_for_seconds=for_seconds)

    # ------- Common functions ---------
    
    def clear(self):
        # Clear the display
        self.device.clear()
    
    def soft_clear(self):
        # Clear the display using a white rectangle as a partial
        self._macros.soft_clear()
    
    # The new clear for background only
    def clear_background(self):
        self._xlog.info("Clearing LCD background interaction.")
        # self.painter.just_paint(background_interaction=BackgroundComm.CLEAR, remove_background_after_painting=True)
        self.painter.just_paint(background_interaction=BackgroundComm.CLEAR)
    
    # The new clear for foreground only
    def clear_foreground(self):
        self._xlog.info("Clearing LCD foreground interaction.")
        self.painter.just_paint(foreground_interaction=ForegroundComm.CLEAR)


    # ------- Matrix-LED-like functions ---------
    
    # def show_kitt_mouth_while_speaking(self):
    #     self._xlog.info(f"👄 Showing KITT mouth on Matrix LED.")
    #     while True:
    #         if not self.is_speaker_busy():
    #             self._xlog.info(f"👄 Stopping KITT mouth on Matrix LED: Speaker not busy")
    #             break
            
    #         if self.read_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR):
    #             self._macros.show_cross()
    #         else:
    #             col_1_value = 0
    #             col_2_value = 0
    #             col_3_value = 2
    #             col_4_value = 4
    #             self._macros.kitt_speaking_effect(col_1_value, col_2_value, col_3_value, col_4_value)
    
    def show_kitt_mouth_while_speaking(self):
        self._xlog.info(f"👄 Showing KITT mouth on LCD.")

        # # We have to wait until the speaker starts being busy, otherwise the mouth effect will self close
        # self._xlog.debug(f"👄 Waiting for Speaker to start speaking.")
        # while not self.is_speaker_busy():
        #     time.sleep(0.01)
        # self._xlog.debug(f"👄 Speaker started speaking.")

        # # Setting what to show and start the painting loop
        # self.painter.set_background_interaction(BackgroundComm.SPEAKING)
        # self.painter.start_or_resume_paint()

        # # Now looping to capture the end of the speaking
        # self._xlog.debug(f"👄 Waiting for Speaker to stop speaking.")
        # while self.is_speaker_busy():
        #     time.sleep(0.01)

        # # Reached here? Stop the painting and clear the interaction
        # self._xlog.debug(f"👄 Stopping KITT mouth on LCD: Speaker not busy")
        # self.painter.stop()
        # self.painter.remove_background_interaction(by_the_end_of_the_painting=True)
        self.painter.paint_into_background_while_speaking(background_interaction=BackgroundComm.SPEAKING)
    
    # def show_kitt_scanner_while_thinking(self):
    #     self._xlog.info(f"🤖 Showing KITT thinking on LCD.")
    #     # self._macros.open_canvas()
    #     while True:
    #         if not self.is_chatbot_busy():
    #             self._xlog.debug(f"🤖 Stopping KITT thinking on LCD.")
    #             break
    #         self._macros.kitt_horizontal_effect()
    #     # self._macros.close_canvas()
    
    def show_kitt_scanner_while_thinking(self):
        self._xlog.info(f"🤖 Showing KITT thinking on LCD.")
        
        # self.painter.set_background_interaction(BackgroundComm.THINKING)
        # self.painter.start_or_resume_paint()

        # self._xlog.info(f"🤖 Waiting for Chatbot to stop thinking")
        # while self.is_chatbot_busy():
        #     time.sleep(0.01)
        # self._xlog.info(f"🤖 Chatbot stopped thinking, clearing")
        
        # self.painter.stop()
        # self.painter.remove_background_interaction(by_the_end_of_the_painting=True)
        # self.clear_background()
        self.painter.paint_into_background_while_thinking(background_interaction=BackgroundComm.THINKING)
    
    def show(self, text: str):
        self._xlog.info(f"🚥 Drawing on LCD: {text}")
        self._macros.draw_something()
    
    # def init_step(self, step: int):
    #     self._xlog.info(f"🚥 Showing init step {step} on LCD")
    #     # For now, just show the step number as a message
    #     self._macros.show_init_step(step)

    def init_phase(self, phase: int):
        self._xlog.info(f"🚥 Showing init phase {phase} on LCD")
        self.painter.just_paint(
            background_interaction=BackgroundComm.INITIAL_PHASE, 
            background_parameter=phase,
            remove_background_after_painting=False)

    # def interaction_holding_percentage(self, percentage: int):
    #     percentage = int(percentage)
    #     self._xlog.info(f"🚥 Showing interaction holding percentage {percentage}% on LCD")
    #     self._macros.show_interaction_holding_percentage(percentage)
    
    def interaction_holding_percentage(self, percentage: int):
        self._xlog.info(f"🚥 Showing interaction holding percentage {percentage}% on LCD")
        self.painter.just_paint(
            background_interaction=BackgroundComm.HOLDER_PERCENTAGE, 
            background_parameter=percentage,
            remove_background_after_painting=True)

    # ------- Communication with Flags ---------
    
    # KITT mouth control: internally, even allowed, we only show it when the speaker is busy.
    def is_speaker_busy(self):
        return self.read_shared_memory_flag(SHARED_SPEAKER_BUSY)
    
    def is_chatbot_busy(self):
        return self.read_shared_memory_flag(SHARED_CHATBOT_BUSY)

    # # LCD busy control: is it already busy?
    # REMOVEME: This is now handled in the parent Xprocess
    # def is_lcd_busy(self):
    #     # return self.read_shared_memory_flag(SHARED_LCD_BUSY)
    #     return self.read_shared_memory_flag(SHARED_MATRIX_BUSY)
    
    # # LCD busy control: set as busy
    # REMOVEME: This is now handled in the parent Xprocess
    # def set_lcd_busy(self):
    #     # self.write_shared_memory_flag(SHARED_LCD_BUSY, True)
    #     self.write_shared_memory_flag(SHARED_MATRIX_BUSY, True)

    # # LCD busy control: unset as busy
    # REMOVEME: This is now handled in the parent Xprocess
    # def unset_lcd_busy(self):
    #     # self.write_shared_memory_flag(SHARED_LCD_BUSY, False)
    #     self.write_shared_memory_flag(SHARED_MATRIX_BUSY, False)

    # LCD idle mode control: is it in idle mode?
    def is_lcd_idle_mode(self):
        return self.read_shared_memory_flag(SHARED_LCD_IDLE_MODE)
