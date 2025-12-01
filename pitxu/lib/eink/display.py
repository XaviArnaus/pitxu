import logging

from pyxavi import Config, dd

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.eink import EinkDisplay, Macros
from pitxu.lib.objects.point import Point
from pitxu.lib.objects import XprocAction
from definitions import SHARED_EINK_BUSY, SHARED_SPEAKER_BUSY, SHARED_EINK_IDLE_MODE

from PIL import Image
import time
import io

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

    IDLE_EYES_CADENCE_SECONDS: float = 10.0
    IDLE_EYES_BLINK_DURATION_SECONDS: float = 0.01

    def get_process_name(self) -> str:
        return "Display"

    def get_display_handler(self) -> EinkDisplay:
        if self._display is not None:
            return self._display
        return None

    def initialize(self):
        self._xlog.info("Initializing Display Worker")
        self._display = EinkDisplay(config=self._xconfig, params=self._xparams)
        self._macros = Macros(config=self._xconfig, params=self._xparams)
        self._display_size = Point(self._xconfig.get("display.size.x"), self._xconfig.get("display.size.y"))

        # Initialize the macros statics
        self._macros.load_or_create_statics()
    
    def finish(self):
        self._xlog.debug("Closing eInk display")
        self._display.close()
        self._xlog.debug("Done finishing Display Worker")
    
    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        # We're busy
        self.set_eink_busy()

        # Shows the message received
        if action == XprocAction.SHOW and param != "":
            self.show(param)
        
        if action == XprocAction.SHOW_IMAGE_EINK and param:
            # Here, param is expected to be an instance of ImageDraw
            self.show_arbitrary_image_while_speaking(param)
        
        if action == XprocAction.SHOW_TALKING_ARBITRARY_EINK and param:
            self.show_arbitrary_text_while_speaking(param)

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
        
        # Now we're not
        self.unset_eink_busy()
    
    def show(self, text: str):
        # Draw the text bubble
        self._xlog.info(f"👀 Showing text bubble on eInk.")
        self._macros.draw_text_bubble(display=self._display, text=text, font=self._display.FONT_MEDIUM)
    
    def show_arbitrary_image_while_speaking(self, image_bytes: str):
        # Show a given image on the eInk display
        self._xlog.info(f"👀 Showing arbitrary image on eInk while speaking.")
        image = Image.frombytes(
            self._display.get_image().mode,
            self._display.get_image().size,
            bytes.fromhex(image_bytes),
            "raw"
        )
        self._display.display_arbitrary_image(image, partial=False)
        while self.is_speaker_busy():
            time.sleep(1)
        time.sleep(1)  # small delay to ensure the user sees the image
        self._xlog.info(f"👀 Finished showing arbitrary image on eInk.")
    
    def show_arbitrary_text_while_speaking(self, text: str):
        self._xlog.info(f"👀 Showing arbitrary text on eInk while speaking.")
        self._macros.arbitrary_text_centered(display=self._display, text=text)
        while self.is_speaker_busy():
            time.sleep(1)
        time.sleep(1)  # small delay to ensure the user sees the image
        self._xlog.info(f"👀 Finished showing arbitrary text on eInk.")

    def splash_ready(self):
        # Draw the ready splash screen
        self._xlog.info(f"👀 Showing ready splash screen on eInk.")
        self._macros.eyes_open(display=self._display)

    def idle(self):
        # Draw the idle screen
        self._xlog.info(f"👀 Showing idle screen on eInk.")
        # There are race conditions if we set this flag here:
        #   The main loop that calls this method may check the flag before we set it here.
        #   To avoid that, we set the flag from the main process before calling this method.
        # self.set_eink_idle_mode()

        # Before we start some time with partial reloads, do a full clear
        # self._display.clear()

        # Draw first the eyes archs
        # self._macros.initial_eyes(display=self._display)
        # self._macros.initial_eyes()
        self._macros.soft_clear(display=self._display)

        # It repeats until the speaker is busy
        should_stop_idle = False
        while not should_stop_idle and self.is_eink_idle_mode():
            # reset the counters and flags
            seconds_waited = 0
            are_eyes_open = False
            # Repeat during the cadence time
            while self.IDLE_EYES_CADENCE_SECONDS > seconds_waited:

                # This is just maintenance, and feels like an ugly fix:
                # Sometimes the eInk's queue receives multiple idle requests, while we're already in idle mode.
                # To avoid piling up those requests, we remove any following idle requests from the queue.
                # This method removes repetitions from the action that is currently being processed.
                # self.remove_following_repetitions_from_queue()

                # wait one second
                time.sleep(1)
                seconds_waited += 1
                # quit if the idle mode is unset from outside
                #   (because we also use the flag in the other direction)
                if not self.is_eink_idle_mode():
                    self._xlog.debug(f"Received a idle mode cancel (idle is now [{self.is_eink_idle_mode()}]).")
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
                # self._macros.eyes_closed(display=self._display)
                self._macros.eyes_closed()
                # and wait a bit
                time.sleep(self.IDLE_EYES_BLINK_DURATION_SECONDS)

        # End of the cadence loop.
        # Setting it from the main process.
        # if self.is_eink_idle_mode():
        #     self.unset_eink_idle_mode()
        self._xlog.info(f"👀 Exiting idle screen on eInk.")


    def splash_startup(self):
        # Draw the startup splash screen
        self._xlog.info(f"👀 Showing startup splash screen on eInk.")
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

    def set_eink_idle_mode(self):
        self.write_shared_memory_flag(SHARED_EINK_IDLE_MODE, True)

    def unset_eink_idle_mode(self):
        self.write_shared_memory_flag(SHARED_EINK_IDLE_MODE, False)

    def is_speaker_busy(self):
        return self.read_shared_memory_flag(SHARED_SPEAKER_BUSY)

    def is_eink_idle_mode(self):
        return self.read_shared_memory_flag(SHARED_EINK_IDLE_MODE)
