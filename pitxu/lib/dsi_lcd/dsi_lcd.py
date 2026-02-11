import time
from PIL import Image

from pyxavi import dd

from pitxu.lib.abstract.xprocess_display_combined import XprocessDisplayCombined
from pitxu.lib.dsi_lcd.device_wrapper import DeviceWrapper
from pitxu.lib.canvas.canvas import Canvas
from pitxu.lib.canvas.macros import Macros
from pitxu.lib.canvas.painter import Painter
from pitxu.lib.canvas.paint_objects import SpeakingBackgroundPaint, ThinkingBackgroundPaint, \
                                            ArbitraryContentForegroundPaint, ArbitraryContentWhileSpeakingForegroundPaint, ArbitraryContentWhileThinkingForegroundPaint, \
                                            StartupForegroundPaint, \
                                            InitPhaseBackgroundPaint, HoldingPercentageBackgroundPaint, \
                                            ClearBackgroundPaint, ClearForegroundPaint
from pitxu.lib.objects.point import Point
from definitions import SHARED_SPEAKER_BUSY, SHARED_CHATBOT_BUSY, SHARED_DSI_LCD_IDLE_MODE

class DsiLcd(XprocessDisplayCombined):
    '''
    Class to control the behaviour of the DSI LCD display inside a sub-process (child)
    '''

    device: DeviceWrapper = None
    canvas: Canvas = None
    macros: Macros = None
    painter: Painter = None
    _display_size: Point = None

    interaction_delays: dict[str, float] = None

    # TODO: Move this into the interaction_delays
    IDLE_EYES_CADENCE_SECONDS: float = 10.0
    IDLE_EYES_BLINK_DURATION_SECONDS: float = 0.01

    LED_TO_LCD_OFFSET_X: int = 250

    VERBOSE_DEBUG: bool = False

    def get_process_name(self) -> str:
        return "DSI_LCD"

    def get_canvas_handler(self) -> Canvas | None:
        if self.canvas is not None:
            return self.canvas
        return None

    def initialize(self):
        self._xlog.info("Initializing LCD Worker")

        # Just have the display size handy
        self._display_size = Point(self._xconfig.get("dsi_lcd.size.x"), self._xconfig.get("dsi_lcd.size.y"))
        self._xparams.set("screen_size", self._display_size)

        # Define which offset do we use IN EACH SIDE of the horizontal screen to emulate the LED Matrix
        self._xparams.set("led_to_lcd_offset_x", self.LED_TO_LCD_OFFSET_X)
        self._xparams.set("apply_led_to_lcd_offset_to_all", True)

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
        # COMMENTED: This is tied with the Idle Mode. Will be revisited later.
        # self._macros.load_or_create_statics()

        # Add the parent's shared memory manager to the params for the painter
        self._xparams.set("shared_memory", self._shared_memory)

        # The Painter that will handle the actual drawing on the canvas and device
        self.painter = Painter(config=self._xconfig, params=self._xparams)

        # Interaction delays
        self.interaction_delays = self._xparams.get("interaction_delays")
        self._xlog.debug("DSI LCD Interaction delays loaded:")
        for key, value in self.interaction_delays.items():
            self._xlog.debug(f"  {key}: {value} seconds")
    
    def initialize_from_main_process(self):
        self._xlog.info("Initializing LCD Worker from Main Process")

        # Just have the display size handy
        self._display_size = Point(self._xconfig.get("dsi_lcd.size.x"), self._xconfig.get("dsi_lcd.size.y"))
        self._xparams.set("screen_size", self._display_size)

        # The canvas to draw on, but basically to let it be available in the main process
        # and deliver font sizes.
        self.canvas = Canvas(config=self._xconfig, params=self._xparams)
        self._xparams.set("canvas", self.canvas)

    def finish(self):
        self._xlog.info("Finalizing DSI LCD Worker")
        self._log_debug("Closing DSI LCD Painter")
        self.painter.close()
        self._log_debug("Closing DSI LCD Canvas")
        self.canvas.close_canvas()
        self._log_debug("Closing DSI LCD Device")
        self.device.close()


    # ------- Foreground functions ---------

    def show(self, text: str):
        # Draw the text bubble
        self._xlog.info(f"👀 Showing text bubble on DSI LCD.")
        self._macros.draw_text_bubble(text=text, font=self.canvas.FONT_MEDIUM)
    
    def show_arbitrary_image_while_speaking(self, image_bytes: dict):
        # Show a given image on the DSI LCD display
        self._xlog.info(f"👀 Showing arbitrary image on DSI LCD while speaking.")
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
        self._xlog.info(f"👀 Showing arbitrary text on DSI LCD while speaking.")

        # Why and How about this approach:
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
            foreground_interaction=ArbitraryContentWhileSpeakingForegroundPaint(parameter=param))
    
    def show_arbitrary_text_while_thinking(self, param: dict):
        self._xlog.info(f"👀 Showing arbitrary text on DSI LCD while thinking.")

        self.painter.paint_into_foreground_while_thinking(
            foreground_interaction=ArbitraryContentWhileThinkingForegroundPaint(parameter=param))
    
    def show_arbitrary_text_on_foreground(self, param: dict):
        self._xlog.info(f"👀 Showing arbitrary text on DSI LCD.")
        for_seconds = param.get("show_for_seconds", self.interaction_delays.get("foreground_notifications", 3.0))
        self.painter.just_paint(
            foreground_interaction=ArbitraryContentForegroundPaint(parameter=param, for_seconds=for_seconds))

    def splash_ready(self):
        # Draw the ready splash screen
        self._xlog.info(f"👀 Showing ready splash screen on DSI LCD.")
        self._macros.eyes_open()

    def idle(self):
        pass
        # # Draw the idle screen
        # self._xlog.info(f"👀 Showing idle screen on DSI LCD.")

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

    def splash_startup(self, for_seconds: float = 3.0):
        # Draw the startup splash screen
        self._xlog.info(f"👀 Showing startup splash screen")
        # The config takes precedence over the parameter that is hardcoded from Main
        show_for_seconds = self.interaction_delays.get("startup_splash", for_seconds)
        self.painter.just_paint(foreground_interaction=StartupForegroundPaint(for_seconds=show_for_seconds))

    # ------- Common functions ---------
    
    def clear(self):
        # Clear the display
        self.device.clear()
    
    def soft_clear(self):
        # Clear the display using a white rectangle as a partial
        self._macros.soft_clear()
    
    # The new clear for background only
    def clear_background(self):
        self._xlog.info("Clearing DSI LCD background interaction.")
        self.painter.just_paint(background_interaction=ClearBackgroundPaint())
    
    # The new clear for foreground only
    def clear_foreground(self):
        self._xlog.info("Clearing DSI LCD foreground interaction.")
        self.painter.just_paint(foreground_interaction=ClearForegroundPaint())


    # ------- Background functions ---------
    
    def show_kitt_mouth_while_speaking(self):
        self._xlog.info(f"👄 Showing KITT mouth on DSI LCD.")
        self.painter.paint_into_background_while_speaking(background_interaction=SpeakingBackgroundPaint(
            delay_between_frames=self.interaction_delays.get("speaking", self.interaction_delays.get("default_delay_between_frames", 0.05))
        ))
    
    def show_kitt_scanner_while_thinking(self):
        self._xlog.info(f"🤖 Showing KITT thinking on DSI LCD.")
        self.painter.paint_into_background_while_thinking(background_interaction=ThinkingBackgroundPaint(
            delay_between_frames=self.interaction_delays.get("thinking", self.interaction_delays.get("default_delay_between_frames", 0.05))
        ))
    def show(self, text: str):
        self._xlog.info(f"🚥 Drawing on DSI LCD: {text}")
        self._macros.draw_something()

    def init_phase(self, phase: int, text: str = None):
        self._xlog.info(f"🚥 Showing init phase {phase} ({text if text else 'No text'}) on DSI LCD")
        self.painter.just_paint(background_interaction=InitPhaseBackgroundPaint(name=f"InitPhaseBackgroundPaint-{phase}", parameter={
            "phase": phase,
            "text": text
        }))
    
    def interaction_holding_percentage(self, percentage: int):
        self._xlog.info(f"🚥 Showing interaction holding percentage {percentage}% on DSI LCD")
        self.painter.just_paint(background_interaction=HoldingPercentageBackgroundPaint(name=f"HoldingPercentageBackgroundPaint-{percentage}", parameter=percentage))
    # ------- Communication with Flags ---------
    
    # KITT mouth control: internally, even allowed, we only show it when the speaker is busy.
    def is_speaker_busy(self):
        return self.read_shared_memory_flag(SHARED_SPEAKER_BUSY)
    
    def is_chatbot_busy(self):
        return self.read_shared_memory_flag(SHARED_CHATBOT_BUSY)


    # DSI LCD idle mode control: is it in idle mode?
    def is_lcd_idle_mode(self):
        return self.read_shared_memory_flag(SHARED_DSI_LCD_IDLE_MODE)
