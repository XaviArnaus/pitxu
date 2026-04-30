from pyxavi import dd
from pitxu.lib.abstract.xprocess_display_foreground import XprocessDisplayForeground
from pitxu.lib.eink.eink import EinkDisplay
# from pitxu.lib.eink.macros import Macros
from pitxu.lib.canvas.canvas import Canvas
from pitxu.lib.canvas.macros import Macros
from pitxu.lib.objects.point import Point
from definitions import SHARED_SPEAKER_BUSY, SHARED_IDLE_MODE

from PIL import Image
import time

class Display(XprocessDisplayForeground):
    '''
    Class to control the behaviour of the eInk display inside a sub-process (child)

    The eInk is pretty slow. We need semaphores and that's why we need the shared memory flags.
    '''

    _display: EinkDisplay = None
    _macros: Macros = None
    _canvas: Canvas = None
    _display_size: Point = None

    DEFAULT_STROKE: int = 1
    COLOR_BLACK: int = 0
    COLOR_WHITE: int = 1

    IDLE_EYES_CADENCE_SECONDS: float = 10.0
    IDLE_EYES_BLINK_DURATION_SECONDS: float = 0.01

    def get_process_name(self) -> str:
        return "Display"

    def get_canvas_handler(self) -> Canvas | None:
        if self._canvas is not None:
            return self._canvas
        return None

    def get_display_handler(self) -> EinkDisplay | None:
        if self._display is not None:
            return self._display
        return None

    def initialize(self):
        self._xlog.info("Initializing eInk Worker")
        self._display_size = Point(self._xconfig.get("eink.size.x"), self._xconfig.get("eink.size.y"))
        self._xparams.set("screen_size", self._display_size)
        self._display = EinkDisplay(config=self._xconfig, params=self._xparams)
        self._xparams.set("device", self._display)
        self._canvas = Canvas(config=self._xconfig, params=self._xparams)
        self._xparams.set("canvas", self._canvas)
        self._macros = Macros(config=self._xconfig, params=self._xparams)

        # Initialize the macros statics
        self._macros.load_or_create_statics()
    
    def initialize_from_main_process(self):
        self._xlog.info("Initializing eInk Worker from Main Process")
        self._display_size = Point(self._xconfig.get("eink.size.x"), self._xconfig.get("eink.size.y"))

        self._xparams.set("screen_size", self._display_size)
        self._canvas = Canvas(config=self._xconfig, params=self._xparams)
    
    def finish(self):
        self._xlog.debug("Closing eInk display")
        self._display.close()
        self._xlog.debug("Done finishing Display Worker")
    
    def show(self, text: str):
        # Draw the text bubble
        self._xlog.info(f"👀 Showing text bubble on eInk.")
        self._macros.draw_text_bubble(text=text, font=self._display.FONT_MEDIUM)
    
    def show_arbitrary_image_while_speaking(self, image_bytes: dict):
        # Show a given image on the eInk display
        self._xlog.info(f"👀 Showing arbitrary image on eInk while speaking.")
        image = Image.frombytes(
            # self._display.get_image().mode,
            # self._display.get_image().size,
            image_bytes["mode"],
            image_bytes["size"],
            bytes.fromhex(image_bytes["image_data"]),
            "raw"
        )
        self._display.display_arbitrary_image(image, partial=False)
        while self.is_speaker_busy():
            time.sleep(1)
        time.sleep(1)  # small delay to ensure the user sees the image
    
    def show_arbitrary_text_while_speaking(self, param: dict):
        self._xlog.info(f"👀 Showing arbitrary text on eInk while speaking.")
        self.show_arbitrary_text_on_foreground(param=param)
        while self.is_speaker_busy():
            time.sleep(1)
        time.sleep(1)  # small delay to ensure the user sees the text
    
    def show_arbitrary_text_while_idle(self, param: dict):
        self._xlog.info(f"👀 Showing arbitrary text on eInk while idle.")
        self.show_arbitrary_text_on_foreground(param=param)
        while self.is_idle_mode_on():
            time.sleep(1)
        time.sleep(1)  # small delay to ensure the user sees the text
    
    def show_arbitrary_text_on_foreground(self, param: dict):
        self._xlog.info(f"👀 Showing arbitrary text on eInk on foreground.")
        self._macros.arbitrary_text_with_icon(
            text=param.get("text", None),
            icon=param.get("icon", None),
            font_size=param.get("font_size", Canvas.FONT_SIZE_BIG),
            header=param.get("header", None),
            font_header_size=param.get("font_header_size", Canvas.FONT_SIZE_HUGE))

    def splash_ready(self):
        # Draw the ready splash screen
        self._xlog.info(f"👀 Showing ready splash screen on eInk.")
        self._macros.eyes_open()

    def idle(self):
        # Draw the idle screen
        self._xlog.info(f"👀 Showing idle screen on eInk.")

        # Draw first the eyes archs
        self._macros.soft_clear()

        # It repeats until the speaker is busy
        should_stop_idle = False
        while not should_stop_idle and self.is_idle_mode_on():
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
                if not self.is_idle_mode_on():
                    self._log_debug(f"Received a idle mode cancel (idle is now [{self.is_idle_mode_on()}]).")
                    should_stop_idle = True
                    break
                # show eyes open if not already shown
                if not are_eyes_open:
                    # self._macros.eyes_open(display=self._display)
                    self._macros.eyes_open()
                    are_eyes_open = True

            # We're here because the cadence time is over or because we should stop idle.
            if not should_stop_idle:
                # show the eyes closed
                self._macros.eyes_closed()
                # and wait a bit
                time.sleep(self.IDLE_EYES_BLINK_DURATION_SECONDS)

    def splash_startup(self, for_seconds: float = 3.0):
        # Draw the startup splash screen
        self._xlog.info(f"👀 Showing startup splash screen on eInk.")
        self._macros.startup_splash()
        time.sleep(for_seconds)
    
    def clear(self):
        # Clear the display
        self._display.clear()
    
    def soft_clear(self):
        # Clear the display using a white rectangle as a partial
        self._macros.soft_clear()

    def is_speaker_busy(self):
        return self.read_shared_memory_flag(SHARED_SPEAKER_BUSY)

    def is_idle_mode_on(self):
        return self.read_shared_memory_flag(SHARED_IDLE_MODE)
