from pyxavi import Config, Dictionary
from pitxu.lib.abstract.device import Device
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.canvas_v2.canvas import Canvas
from pitxu.lib.canvas_v2.macros_background import MacrosBackground
from pitxu.lib.canvas_v2.macros_foreground import MacrosForeground
from pitxu.lib.canvas_v2.macros_layout import MacrosLayout
from pitxu.lib.canvas_v2.macros_overlay import MacrosOverlay
from pitxu.lib.canvas_v2.painter import Painter, PainterQueue
from pitxu.lib.canvas_v2.painting_command import *
from pitxu.lib.canvas_v2.painting_object import PaintingObject, ForegroundPaint, BackgroundPaint, OverallPaint
from pitxu.lib.objects.point import Point

from definitions import SHARED_SPEAKER_BUSY, \
                        SHARED_DSI_LCD_BUSY, \
                        SHARED_MICROPHONE_MUTED, \
                        SHARED_CHATBOT_BUSY, \
                        SHARED_CHATBOT_ANSWER_IS_ERROR, \
                        SHARED_DSI_LCD_IDLE_MODE, \
                        SHARED_NETWORK_BUSY, \
                        SHARED_VAD_DETECTED, \
                        SHARED_SUPPORT_BUSY, \
                        SHARED_STT_BUSY, \
                        SHARED_TRANSCRIBER_BUSY

class Visualizer(PyXavi):
    """
    This is the entry point for the visualization work.
    It is meant to be instantiated by the display-dependant-xprocess class (dsi_lcd, ...),
        so visualization engine (canvas, macros, painter, ...) can be shared across different display implementations.
    """

    device: Device = None
    canvas: Canvas = None
    painter: Painter = None
    macros_layout: MacrosLayout = None
    macros_overlay: MacrosOverlay = None
    macros_foreground: MacrosForeground = None
    macros_background: MacrosBackground = None

    interaction_delays: dict[str, float] = None
    display_size: Point = None

    DEFAULT_FOREGROUND_MAINTAIN_SECONDS: float = 5.0

    def __init__(self, config: Config, params: Dictionary):
        super(Visualizer, self).init_pyxavi(config, params)

        # The display size depends on the display implementation, so it should be provided by the display-dependant-xprocess class (dsi_lcd, ...).
        if params.key_exists("display_size"):
            self._display_size = params.get("display_size")
            params.set("screen_size", self._display_size)

        elif params.key_exists("screen_size"):
            self._display_size = params.get("screen_size")

        else:
            raise ValueError("'display_size' or 'screen_size' parameter is required for Visualizer.")
        
        # The device is also display-dependant, so it should be provided by the display-dependant-xprocess class (dsi_lcd, ...).
        if params.key_exists("device"):
            self.device = params.get("device")

        else:
            raise ValueError("'device' parameter is required for Visualizer.")

        # We instantiate now the generic stuff that we need from here on.
        # Canvas needs:
        #   - device_config_prefix: to read the specific configuration for the canvas ("dsi_lcd", ...)
        #   - screen_size: to know the size of the canvas to create. Can also read from the config.
        #   - font_file: to be instantiate the fonts in every needed size. Can also read from the config.
        #   - color_mode: to know if we need to create RGBA or RGB images. Can also read from the config.
        self.canvas = Canvas(config, params)
        # All Macros needs:
        #   - canvas: to know where to paint to.
        params.set("canvas", self.canvas)
        self.macros_layout = MacrosLayout(config, params)
        self.macros_overlay = MacrosOverlay(config, params)
        self.macros_foreground = MacrosForeground(config, params)
        self.macros_background = MacrosBackground(config, params)

        # The painter is the one that will control the painting loop and trigger the macros to paint.
        # It needs:
        #   - canvas: to know where to paint to.
        #   - layout_info: to know the layout of the screen and where to paint the different interactions.
        #   - layout_position_to_queue_name: to know where to queue the different interactions based on their layout position.
        #   - drawing_callbacks: to know which macros to trigger for each interaction type.
        params.set("drawing_callbacks", {
            "foreground_frame":  {
                "callback": self.macros_layout.draw_foreground_frame,
                "parameters": {
                    "padding": 10,
                    "radius": 10,
                }
            },
            "overlay_frame": {
                "callback": self.macros_layout.draw_overall_full_frame,
                "parameters": {
                    "padding": 10,
                    "radius": 10,
                    "frame_color": self.canvas.COLOR_WHITE,
                    "opacity": 0.75,
                }
            },
            "base_frame_for_display_area": {
                "callback": self.macros_layout.base_frame_for_display_area,
                "parameters": {
                    "display_area": "full_screen",
                }
            },
            "soft_full_clear": {
                "callback": self.macros_layout.soft_full_clear,
                "parameters": {}
            },
            "display": {
                "callback": self.device.display,
                "parameters": {}
            },
        })
        params.set("layout_info", self.macros_layout.get_layout_info())
        params.set("layout_position_to_queue_name", {
            "top_left": PainterQueue.BACKGROUND,
            "top_right": PainterQueue.FOREGROUND,
            "full_screen": PainterQueue.OVERALL
        })
        self.painter = Painter(config, params)

        self.interaction_delays = self._xparams.get("interaction_delays", {})

        # ⚠️ There has to be a list of shared memory flags that we monitor forever, and the related callbacks never get removed.
        # Examples:
        #   - SHARED_SPEAKER_BUSY: to trigger the speaking animation when the speaker is busy.
        #   - SHARED_CHATBOT_BUSY: to trigger the thinking animation when the chatbot is busy.
        #   - SHARED_DSI_LCD_IDLE_MODE: to trigger the idle animation when the DSI LCD is in idle mode.
        #   - SHARED_NETWORK_BUSY: to trigger a network animation when the network is busy for too long.
        #   - other status-like flags that we want to monitor to trigger some visualization when they are activated.
        # The idea is to set them up only once here, in the Visualizer, and never worry about them again, without needing to set them up on every interaction that needs them.

        self._xlog.debug("Initialized Visualizer.")
    
    # We need to place here the methods that trigger the visualization. 
    # They are meant to encapsulate the Paint creation with all the Painter parameters, 
    # leaving a simple interface to trigger from the dsi_lcd or other display-dependant-xprocess class.

    # TODO: Notes for a the next iteration on the implementation:
    #   - When the `for_seconds` is not provided, the `ignore_maintain_time` is always True, False otherwise.
    #       Therefore, we could simplify the implementation controlling both inside (in the engine itself)
    #   - Apparently, all foreground have `final_screen_clearing=True` and `remove_interaction_after_painting=True`.
    #       Do we want to keep it flexible or just set it as default for all foreground paints?

    # ---- FOREGROUND PAINTS ----

    def arbitrary_text(self, params: dict):

        self.painter.paint(
            PaintingObject(
                foreground=ForegroundPaint(
                    name="ArbitraryContentForegroundPaint",
                    command=ForegroundCommand(ForegroundCommand.ARBITRARY_TEXT_ICON),

                    drawing_callback=self.macros_foreground.draw_arbitrary_text_with_icon,
                    drawing_callback_parameters=params,

                    maintain_paint_for_seconds=params.get("for_seconds", self.DEFAULT_FOREGROUND_MAINTAIN_SECONDS),

                    # final_screen_clearing=True,
                    # remove_interaction_after_painting=True,
                    ignore_maintain_time=False
                )
            )
        )

    def arbitrary_text_while_speaking(self, params: dict):

        self.painter.paint(
            PaintingObject(
                foreground=ForegroundPaint(
                    name="ArbitraryContentWhileSpeakingForegroundPaint",
                    command=ForegroundCommand(ForegroundCommand.ARBITRARY_TEXT_ICON),

                    while_shared_memory_flag=SHARED_SPEAKER_BUSY,
                    while_shared_memory_flag_value=True,

                    drawing_callback=self.macros_foreground.draw_arbitrary_text_with_icon,
                    drawing_callback_parameters=params,

                    # final_screen_clearing=True,
                    # remove_interaction_after_painting=True,
                    # ignore_maintain_time=True
                )
            )
        )
    
    def arbitrary_text_while_thinking(self, params: dict):

        self.painter.paint(
            PaintingObject(
                foreground=ForegroundPaint(
                    name="ArbitraryContentWhileThinkingForegroundPaint",
                    command=ForegroundCommand(ForegroundCommand.ARBITRARY_TEXT_ICON),

                    while_shared_memory_flag=SHARED_CHATBOT_BUSY,
                    while_shared_memory_flag_value=True,

                    drawing_callback=self.macros_foreground.draw_arbitrary_text_with_icon,
                    drawing_callback_parameters=params,

                    # final_screen_clearing=True,
                    # remove_interaction_after_painting=False,
                    # ignore_maintain_time=True
                )
            )
        )
    
    def arbitrary_text_while_idle(self, params: dict):

        self.painter.paint(
            PaintingObject(
                foreground=ForegroundPaint(
                    name="ArbitraryContentWhileIdleForegroundPaint",
                    command=ForegroundCommand(ForegroundCommand.ARBITRARY_TEXT_ICON),

                    while_shared_memory_flag=SHARED_DSI_LCD_IDLE_MODE,
                    while_shared_memory_flag_value=True,

                    drawing_callback=self.macros_foreground.draw_arbitrary_text_with_icon,
                    drawing_callback_parameters=params,

                    maintain_paint_for_seconds=params.get("for_seconds", self.DEFAULT_FOREGROUND_MAINTAIN_SECONDS),

                    # final_screen_clearing=True,
                    # remove_interaction_after_painting=True,
                    ignore_maintain_time=False,
                )
            )
        )
    
    def arbitrary_while_user_speaking(self, params: dict):

        self.painter.paint(
            PaintingObject(
                foreground=ForegroundPaint(
                    name="ArbitraryContentWhileUserSpeakingForegroundPaint",
                    command=ForegroundCommand(ForegroundCommand.ARBITRARY_TEXT_ICON),

                    while_shared_memory_flag=SHARED_TRANSCRIBER_BUSY,
                    while_shared_memory_flag_value=True,

                    drawing_callback=self.macros_foreground.draw_arbitrary_text_with_icon,
                    drawing_callback_parameters=params,

                    for_seconds=params.get("for_seconds", self.DEFAULT_FOREGROUND_MAINTAIN_SECONDS),

                    # final_screen_clearing=True,
                    # remove_interaction_after_painting=True,
                    ignore_maintain_time=False
                )
            )
        )
    
    def error(self, params: dict):

        self.painter.paint(
            PaintingObject(
                foreground=ForegroundPaint(
                    name="ErrorForegroundPaint",
                    command=ForegroundCommand(ForegroundCommand.ARBITRARY_TEXT_ICON),

                    drawing_callback=self.macros_foreground.draw_arbitrary_text_with_icon,
                    drawing_callback_parameters={
                        "text": params.get("text", ""),
                        "icon": "❌",
                        "font_size": params.get("font_size", 24),
                        "header": "Error",
                        "font_header_size": params.get("font_header_size", 32),
                        "padding": params.get("padding", 5)
                    },

                    for_seconds=params.get("for_seconds", self.DEFAULT_FOREGROUND_MAINTAIN_SECONDS),

                    # final_screen_clearing=True,
                    # remove_interaction_after_painting=True,
                    ignore_maintain_time=False
                )
            )
        )
    
    def startup_with_phase(self, params: dict):

        self.painter.paint(
            PaintingObject(
                foreground=ForegroundPaint(
                    name=f"StartupWithPhaseForegroundPaint",
                    command=ForegroundCommand(ForegroundCommand.STARTUP_WITH_PHASE),

                    drawing_callback=self.macros_foreground.draw_combined_init_phase,
                    drawing_callback_parameters=params,
                    cache_control_parameters=["phase"],

                    # final_screen_clearing=True,
                    # remove_interaction_after_painting=False,
                    overwrite_current_interaction_with_same_type = True,
                )
            )
        )
    
    # ---- OVERALL PAINTS ----
    
    def code_block(self, params: dict):

        self.painter.paint(
            PaintingObject(
                overall=OverallPaint(
                    name="CodeBlockOverallPaint",
                    command=OverallCommand(OverallCommand.CODE_BLOCK),

                    drawing_callback=self.macros_overlay.draw_code_block,
                    drawing_callback_parameters={
                        "text": params.get("text", ""),
                        # "font_size": params.get("font_size", 20),
                        # "padding": params.get("padding", 5)
                    },

                    for_seconds=params.get("for_seconds", self.DEFAULT_FOREGROUND_MAINTAIN_SECONDS),

                    # final_screen_clearing=True,
                    # remove_interaction_after_painting=True,
                    ignore_maintain_time=False
                )
            )
        )
    
    def code_block_while_speaking(self, params: dict):

        self.painter.paint(
            PaintingObject(
                overall=OverallPaint(
                    name="CodeBlockWhileSpeakingOverallPaint",
                    command=OverallCommand(OverallCommand.CODE_BLOCK),

                    while_shared_memory_flag=SHARED_SPEAKER_BUSY,
                    while_shared_memory_flag_value=True,

                    drawing_callback=self.macros_overlay.draw_code_block,
                    drawing_callback_parameters={
                        "text": params.get("text", ""),
                        # "font_size": params.get("font_size", 20),
                        # "padding": params.get("padding", 5)
                    },

                    # final_screen_clearing=True,
                    # remove_interaction_after_painting=True,
                    # ignore_maintain_time=True
                )
            )
        )
    
    def text_block(self, params: dict):

        self.painter.paint(
            PaintingObject(
                overall=OverallPaint(
                    name="TextBlockOverallPaint",
                    command=OverallCommand(OverallCommand.TEXT_BLOCK),

                    drawing_callback=self.macros_overlay.draw_text_block,
                    drawing_callback_parameters={
                        "text": params.get("text", ""),
                        # "font_size": params.get("font_size", 20),
                        # "padding": params.get("padding", 5)
                    },

                    for_seconds=params.get("for_seconds", self.DEFAULT_FOREGROUND_MAINTAIN_SECONDS),

                    # final_screen_clearing=True,
                    # remove_interaction_after_painting=True,
                    ignore_maintain_time=False
                )
            )
        )
    
    def text_block_while_speaking(self, params: dict):

        self.painter.paint(
            PaintingObject(
                overall=OverallPaint(
                    name="TextBlockWhileSpeakingOverallPaint",
                    command=OverallCommand(OverallCommand.TEXT_BLOCK),

                    while_shared_memory_flag=SHARED_SPEAKER_BUSY,
                    while_shared_memory_flag_value=True,

                    drawing_callback=self.macros_overlay.draw_text_block,
                    drawing_callback_parameters={
                        "text": params.get("text", ""),
                        # "font_size": params.get("font_size", 20),
                        # "padding": params.get("padding", 5)
                    },

                    # final_screen_clearing=True,
                    # remove_interaction_after_painting=True,
                    # ignore_maintain_time=True
                )
            )
        )
    
    # ---- COMMON PAINTS ----

    def clear_foreground(self):

        self.painter.paint(
            PaintingObject(
                foreground=ForegroundPaint(
                    name="ClearForegroundPaint",
                    command=ForegroundCommand(ForegroundCommand.CLEAR),

                    drawing_callback=self.macros_layout.base_frame_for_display_area,
                    drawing_callback_parameters={
                        "display_area": "top_right",
                    },

                    # final_screen_clearing=False,
                    remove_interaction_after_painting=True
                )
            )
        )
    
    def clear_background(self):

        self.painter.paint(
            PaintingObject(
                background=BackgroundPaint(
                    name="ClearBackgroundPaint",
                    command=BackgroundCommand(BackgroundCommand.CLEAR),

                    drawing_callback=self.macros_layout.base_frame_for_display_area,
                    drawing_callback_parameters={
                        "display_area": "top_left",
                    },

                    # final_screen_clearing=False,
                    remove_interaction_after_painting=True
                )
            )
        )
    
    # ---- BACKGROUND PAINTS ----

    def kitt_mouth_while_speaking(self):

        self.painter.paint(
            PaintingObject(
                background=BackgroundPaint(
                    name="KittMouthWhileSpeakingBackgroundPaint",
                    command=BackgroundCommand(BackgroundCommand.SPEAKING),

                    while_shared_memory_flag=SHARED_SPEAKER_BUSY,
                    while_shared_memory_flag_value=True,

                    # The parameters on this call are added during the painting stage.
                    #   - current_loop_iteration
                    #   - max_loop_iterations
                    # They are used by the macro method to calculate the phase to draw.
                    drawing_callback=self.macros_background.draw_kitt_speaking_effect,
                    drawing_callback_parameters={},
                    cache_control_parameters=["current_loop_iteration"],

                    loop_iterations=8,
                    delay_between_frames=self.interaction_delays.get("speaking", 
                                                                    self.interaction_delays.get("default_delay_between_frames", 
                                                                                                0.05)),

                    final_area_clearing=True,
                    remove_interaction_after_painting=False

                    # TODO: Maybe we should do a soft clear after removing the interaction, 
                    # to avoid the persistence of the last phase of the effect on the screen, which can be a bit weird.
                )
            )
        )
    
    def kitt_scanner_while_thinking(self):

        self.painter.paint(
            PaintingObject(
                background=BackgroundPaint(
                    name="KittScannerWhileThinkingBackgroundPaint",
                    command=BackgroundCommand(BackgroundCommand.THINKING),

                    while_shared_memory_flag=SHARED_CHATBOT_BUSY,
                    while_shared_memory_flag_value=True,

                    # The parameters on this call are added during the painting stage.
                    #   - current_loop_iteration
                    #   - max_loop_iterations
                    # They are used by the macro method to calculate the phase to draw.
                    drawing_callback=self.macros_background.draw_kitt_horizontal_effect,
                    drawing_callback_parameters={},
                    cache_control_parameters=["current_loop_iteration"],

                    loop_iterations=16,
                    delay_between_frames=self.interaction_delays.get("thinking", 
                                                                    self.interaction_delays.get("default_delay_between_frames", 
                                                                                                0.05)),

                    final_area_clearing=True,
                    remove_interaction_after_painting=False

                    # TODO: Maybe we should do a soft clear after removing the interaction, 
                    # to avoid the persistence of the last phase of the effect on the screen, which can be a bit weird.
                )
            )
        )
    
    def holding_percentage(self, param: dict):

        self.painter.paint(
            PaintingObject(
                background=BackgroundPaint(
                    name=f"HoldingPercentageBackgroundPaint",
                    command=BackgroundCommand(BackgroundCommand.HOLDER_PERCENTAGE),

                    drawing_callback=self.macros_background.draw_interaction_holding_percentage,
                    drawing_callback_parameters=param,
                    cache_control_parameters=["percentage"],

                    overwrite_current_interaction_with_same_type=True,

                    final_screen_clearing=False,
                    remove_interaction_after_painting=False
                )
            )
        )
    