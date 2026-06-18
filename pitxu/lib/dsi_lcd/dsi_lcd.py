from pitxu.lib.abstract.xprocess_display_combined import XprocessDisplayCombined
from pitxu.lib.dsi_lcd.device_wrapper import DeviceWrapper
from pitxu.lib.canvas_v2.canvas import Canvas
from pitxu.lib.canvas_v2.painting_object import *
from pitxu.lib.canvas_v2.visualizer import Visualizer
from pitxu.lib.objects.point import Point

class DsiLcd(XprocessDisplayCombined):
    '''
    Class to control the behaviour of the DSI LCD display inside a sub-process (child)
    '''

    device: DeviceWrapper = None
    canvas: Canvas = None
    visualizer: Visualizer = None
    _display_size: Point = None

    interaction_delays: dict[str, float] = None

    VERBOSE_DEBUG: bool = False

    def get_process_name(self) -> str:
        return "DsiLcd"

    def get_canvas_handler(self) -> Canvas | None:
        if self.canvas is not None:
            return self.canvas
        return None

    def initialize(self):
        self._xlog.info("Initializing LCD Worker")

        # Just have the display size handy
        self._display_size = Point(self._xconfig.get("dsi_lcd.size.x"), self._xconfig.get("dsi_lcd.size.y"))
        self._xparams.set("screen_size", self._display_size)

        # The given device. It handles the interaction with the actual hardware or the mocking.
        self.device = DeviceWrapper(config=self._xconfig, params=self._xparams)
        self._xparams.set("device", self.device)
        # The canvas to draw on
        self.canvas = Canvas(config=self._xconfig, params=self._xparams)
        self._xparams.set("canvas", self.canvas)

        # Add the parent's shared memory manager to the params for the painter
        self._xparams.set("shared_memory", self._shared_memory)

        # The Visualizer that will handle the painting of the interactions on the canvas and device, using the Painter.
        # It expects in xparams:
        #   - interaction_delays: dict[str, float]: the delays to use for the different interactions, to be passed to the Painter and used in the painting objects.
        self.visualizer = Visualizer(config=self._xconfig, params=self._xparams)

        self.log_summary("DSI LCD Initialization", [
            ("Display Size", f"{self._display_size.x}x{self._display_size.y}")
        ])

        # Interaction delays
        self.interaction_delays = self._xparams.get("interaction_delays")
        self.log_summary("DSI LCD Interaction Delays", [(key, f"{value} seconds") for key, value in self.interaction_delays.items()])
    
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
        self._log_debug("Closing DSI LCD Canvas")
        self.canvas.close_canvas()
        self._log_debug("Closing DSI LCD Device")
        self.device.close()
        self._xlog.info("Done finishing DSI LCD Worker")

    # ------- Foreground functions ---------

    def show_arbitrary_text_while_speaking(self, param: dict):
        self._xlog.info(f"👀 Showing arbitrary text on DSI LCD while speaking.")

        self.visualizer.arbitrary_text_while_speaking(param)
    
    def show_arbitrary_text_while_thinking(self, param: dict):
        self._xlog.info(f"👀 Showing arbitrary text on DSI LCD while thinking.")

        self.visualizer.arbitrary_text_while_thinking(param)
    
    def show_arbitrary_text_while_idle(self, param: dict):
        self._xlog.info(f"👀 Showing arbitrary text on DSI LCD while idle.")

        if "for_seconds" not in param:
            param["for_seconds"] = self.interaction_delays.get("idle_status_foreground_notification", 15.0)

        self.visualizer.arbitrary_text_while_idle(param)
    
    def show_arbitrary_icon_on_foreground_while_user_speaking(self, param: dict):
        self._xlog.info(f"👀 Showing arbitrary icon on DSI LCD while the user is speaking.")

        self.visualizer.arbitrary_while_user_speaking(param)
    
    def show_arbitrary_text_on_foreground(self, param: dict):
        self._xlog.info(f"👀 Showing arbitrary text on DSI LCD.")
        
        if "for_seconds" not in param:
            param["for_seconds"] = self.interaction_delays.get("foreground_notification", 3.0)

        self.visualizer.arbitrary_text(param)

    def idle(self):
        pass
    
    def show_error(self, text: str, for_seconds: float = 3.0):
        # Draw the error splash screen
        self._xlog.info(f"👀 Showing error screen for {for_seconds} seconds")
        
        param = {
            "text": text,
            "font_size": self.canvas.FONT_SIZE_MEDIUM,
            "font_header_size": self.canvas.FONT_SIZE_BIG
        }
        if for_seconds is None:
            param["for_seconds"] = self.interaction_delays.get("error", 3.0)

        self.visualizer.error(param)

    def show_code_block(self, param: dict):
        self._xlog.info(f"👀 Showing code block on DSI LCD.")
        
        # We receive "code" but we want "text".
        # If we fix this in the future (in the caller side), be prepared here.
        if "code" in param and "text" not in param:
            param["text"] = param["code"]
        if "for_seconds" not in param:
            param["for_seconds"] = self.interaction_delays.get("code_block", 10.0)

        self.visualizer.code_block(param)
    
    def show_code_block_while_speaking(self, param: dict):
        self._xlog.info(f"👀 Showing code block on DSI LCD while speaking.")

        # We receive "code" but we want "text".
        # If we fix this in the future (in the caller side), be prepared here.
        if "code" in param and "text" not in param:
            param["text"] = param["code"]
        
        self.visualizer.code_block_while_speaking(param)
    
    def show_text_block(self, param: dict):
        self._xlog.info(f"👀 Showing text block on DSI LCD.")
        
        if "for_seconds" not in param:
            param["for_seconds"] = self.interaction_delays.get("text_block", 10.0)

        self.visualizer.text_block(param)
    
    def show_text_block_while_speaking(self, param: dict):
        self._xlog.info(f"👀 Showing text block on DSI LCD while speaking.")
        
        self.visualizer.text_block_while_speaking(param)
    
    def init_phase(self, phase: int, text: str = None):
        self._xlog.info(f"🚥 Showing init phase {phase} ({text if text else 'No text'}) on LCD")
        
        param = {
            "phase": phase,
            "text": text
        }
        self.visualizer.startup_with_phase(param)

    # ------- Common functions ---------
    
    def clear(self):
        # Clear the display.
        # Passing the display size just in case we want to clear the mocked LCD, to have a black image of the correct size.
        self.device.clear(screen_size=(self._display_size.x, self._display_size.y))
    
    def soft_clear(self):
        self.clear_background()
        self.clear_foreground()
    
    def clear_background(self):
        self._xlog.info("Clearing DSI LCD background interaction.")
        self.visualizer.clear_background()
    
    def clear_foreground(self):
        self._xlog.info("Clearing DSI LCD foreground interaction.")
        self.visualizer.clear_foreground()


    # ------- Background functions ---------
    
    def show_kitt_mouth_while_speaking(self):
        self._xlog.info(f"👄 Showing KITT mouth on DSI LCD.")
        self.visualizer.kitt_mouth_while_speaking()
    
    def show_kitt_scanner_while_thinking(self):
        self._xlog.info(f"🤖 Showing KITT thinking on DSI LCD.")
        self.visualizer.kitt_scanner_while_thinking()

    def interaction_holding_percentage(self, percentage: int):
        self._xlog.info(f"🚥 Showing interaction holding percentage {percentage}% on DSI LCD")
        param = {
            "percentage": percentage
        }
        self.visualizer.holding_percentage(param)
