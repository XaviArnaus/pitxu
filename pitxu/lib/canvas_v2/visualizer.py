import time

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.device import Device
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.canvas_v2.canvas import Canvas
from pitxu.lib.canvas_v2.animations import Animations
from pitxu.lib.canvas_v2.layout_info import LayoutInfo, DisplayArea
from pitxu.lib.canvas_v2.macros.macros_background import MacrosBackground
from pitxu.lib.canvas_v2.macros.macros_buttons import MacrosButtons
from pitxu.lib.canvas_v2.macros.macros_foreground import MacrosForeground
from pitxu.lib.canvas_v2.macros.macros_status import MacrosStatus
from pitxu.lib.canvas_v2.macros.macros_layout import MacrosLayout
from pitxu.lib.canvas_v2.macros.macros_overlay import MacrosOverlay
from pitxu.lib.canvas_v2.painter.painter import Painter, PainterQueue
from pitxu.lib.canvas_v2.painter.painting_command import OverallCommand, ForegroundCommand, StatusCommand, ButtonsCommand, BackgroundCommand, AnimationsCommand
from pitxu.lib.canvas_v2.painter.paint_object import PaintObject, BasePaint, ForegroundPaint, BackgroundPaint, OverallPaint, StatusPaint, AnimationPaint, ButtonsPaint
from pitxu.lib.canvas_v2.buttons import BUTTONS, COLUMN_TO_DISPLAY_AREA
from pitxu.lib.objects.point import Point

from definitions import (
    SHARED_SPEAKER_BUSY,
    SHARED_CHATBOT_BUSY,
    SHARED_DSI_LCD_IDLE_MODE,
    SHARED_NETWORK_BUSY,
    SHARED_TRANSCRIBER_BUSY,
    SHARED_SPEAKER_LEVEL,
)
from pitxu.lib.objects.rectangle import Rectangle
from pitxu.lib.objects.size import Size

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
    macros_status: MacrosStatus = None
    macros_background: MacrosBackground = None
    macros_buttons: MacrosButtons = None
    animations: Animations = None

    interaction_delays: dict[str, float] = None
    layout_info: dict[str, dict[str, Rectangle]] = None
    display_size: Point = None
    animation_sizes_per_display_area: dict[str, Size] = None

    DEFAULT_FOREGROUND_MAINTAIN_SECONDS: float = 5.0

    BUTTONS_COLUMN_TO_QUEUE: dict[str, str] = {
        "left": PainterQueue.BUTTONS_LEFT,
        "right": PainterQueue.BUTTONS_RIGHT,
    }

    VERBOSE_DEBUG: bool = False

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
        params.set("canvas", self.canvas)

        # LayoutInfo needs:
        #   - canvas: to know where to paint to.
        layout_info_class: LayoutInfo = LayoutInfo(config, params)
        self.layout_info = layout_info_class.get_layout_info()
        params.set("layout_info_class", layout_info_class)
        params.set("layout_info", self.layout_info)
        
        # Animations needs:
        #   - Layout info: to calculate the size to which we need to resize the animation frames, based on the display area sizes.
        self.animation_sizes_per_display_area = self._prepare_animation_sizes()
        params.set("animation_sizes", self.animation_sizes_per_display_area.values())
        self.animations = Animations(config, params)
        params.set("animations", self.animations)

        # All Macros need:
        #   - canvas: to know where to paint to.
        #   - layout_info_class: to know the layout of the screen and where to paint the different interactions.
        #   - animations: to be able to use the loaded animations in the macros that need them.
        self.macros_layout = MacrosLayout(config, params)
        self.macros_overlay = MacrosOverlay(config, params)
        self.macros_foreground = MacrosForeground(config, params)
        self.macros_status = MacrosStatus(config, params)
        self.macros_background = MacrosBackground(config, params)
        self.macros_buttons = MacrosButtons(config, params)

        # The painter is the one that will control the painting loop and trigger the macros to paint.
        # It needs:
        #   - canvas: to know where to paint to.
        #   - layout_info: to know the layout of the screen and where to paint the different interactions.
        #   - layout_position_to_queue_name: to know where to queue the different interactions based on their layout position.
        #   - drawing_callbacks: to know which macros to trigger for each interaction type.
        #   - painter_queues: to know the queues to use for the different interactions.
        #   - painter_priorities: to know the interactions that have priority over others in each queue (that will remove previous ones in the queue)
        #   - exception_loop_interactions: to know the interactions that will not be considered in the loop execution time calculation.
        #   - painter_queues_with_paints_that_slows_down_the_loop: to know which queues we should consider that their paints can slow down the loop, to be able to log warnings when the loop is taking too long, and identify which interaction is causing it.
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
                    "display_area": DisplayArea.OVERALL,
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
        params.set("layout_position_to_queue_name", {
            DisplayArea.ANIMATIONS: PainterQueue.ANIMATIONS,
            DisplayArea.BACKGROUND: PainterQueue.BACKGROUND,
            DisplayArea.MESSAGES: PainterQueue.FOREGROUND,
            DisplayArea.STATUS: PainterQueue.STATUS,
            DisplayArea.BUTTONS_LEFT: PainterQueue.BUTTONS_LEFT,
            DisplayArea.BUTTONS_RIGHT: PainterQueue.BUTTONS_RIGHT,
            DisplayArea.OVERALL: PainterQueue.OVERALL
        })
        # ⚠️ The ORDER here is the painting order, from the bottom layer to the top one.
        #   - OVERALL has to be the LAST one: it covers the whole screen (overlays, code and text blocks).
        #   - Anything new that has its own display area goes BEFORE OVERALL, otherwise it would paint over the overlays.
        params.set("painter_queues", [
            PainterQueue.BACKGROUND,
            PainterQueue.ANIMATIONS,
            PainterQueue.STATUS,
            PainterQueue.FOREGROUND, 
            PainterQueue.BUTTONS_LEFT,
            PainterQueue.BUTTONS_RIGHT,
            PainterQueue.OVERALL,
        ])
        params.set("painter_priorities", {
            PainterQueue.BACKGROUND: [BackgroundCommand.SPEAKING]
        })
        params.set("painter_exception_loop_interactions", {
            PainterQueue.BACKGROUND: [BackgroundCommand.SPEAKING, BackgroundCommand.NETWORKING],
            PainterQueue.ANIMATIONS: [AnimationsCommand.THINKING]
        })
        # The queues in which a paint is static and don't need fast loop iterations.
        # ⚠️ A persistent paint in any queue NOT listed here (like the buttons panel) prevents the loop from slowing down.
        params.set("painter_queues_with_paints_that_slow_down_the_loop", [
            PainterQueue.FOREGROUND,
            PainterQueue.STATUS,
            PainterQueue.OVERALL,
            PainterQueue.BUTTONS_LEFT,
            PainterQueue.BUTTONS_RIGHT
        ])
        self.painter = Painter(config, params)

        self.interaction_delays = params.get("interaction_delays", {})

        logging_parts = [
            ("display_size", self._display_size),
            ("device", self.device.__class__.__name__),
            ("canvas", self.canvas.__class__.__name__),
            ("macros_layout", self.macros_layout.__class__.__name__),
            ("macros_overlay", self.macros_overlay.__class__.__name__),
            ("macros_foreground", self.macros_foreground.__class__.__name__),
            ("macros_status", self.macros_status.__class__.__name__),
            ("macros_background", self.macros_background.__class__.__name__),
            ("drawing_callbacks", list(params.get("drawing_callbacks", {}).keys())),
            ("layout_position_to_queue_name", params.get("layout_position_to_queue_name", {})),
            ("painter_queues", params.get("painter_queues", [])),
            ("painter_priorities", params.get("painter_priorities", {})),
            ("painter_exception_loop_interactions", params.get("painter_exception_loop_interactions", {})),
            ("painter_queues_with_paints_that_slow_down_the_loop", params.get("painter_queues_with_paints_that_slow_down_the_loop", [])),
            ("interaction_delays", self.interaction_delays),
        ]
        for display_area, size in self.animation_sizes_per_display_area.items():
            logging_parts.append((f"Animation Size for {display_area}", size))
        self.log_summary("Visualizer initialized", logging_parts, attend_verbose_debug_flag=True)

        # ⚠️ There has to be a list of shared memory flags that we monitor forever, and the related callbacks never get removed.
        # Examples:
        #   - SHARED_SPEAKER_BUSY: to trigger the speaking animation when the speaker is busy.
        #   - SHARED_CHATBOT_BUSY: to trigger the thinking animation when the chatbot is busy.
        #   - SHARED_DSI_LCD_IDLE_MODE: to trigger the idle animation when the DSI LCD is in idle mode.
        #   - SHARED_NETWORK_BUSY: to trigger a network animation when the network is busy for too long.
        #   - other status-like flags that we want to monitor to trigger some visualization when they are activated.
        # The idea is to set them up only once here, in the Visualizer, and never worry about them again, without needing to set them up on every interaction that needs them.
        self._setup_buttons_monitoring()

        self._xlog.debug("Initialized Visualizer.")
    
    def load_animations(self):
        # It takes time, and because the Visualizer is loaded with the display, 
        #   which is loaded during the initialization of the Interactions, 
        #   which is the very first thing to do in main,
        # We individualize it outside so we can print something before 
        #   and don't let the user with a black screen meanwhile.
        # Then, it's mandatory to be called through a XprocessAction

        self._xlog.info("Loading animations in Visualizer...")
        self.animations.load_animations()
        self._xlog.info("Animations loaded in Visualizer.")
    
    def close(self):
        self._xlog.debug("Closing Visualizer...")
        self.painter.close()
        self.canvas.close_canvas()
        self._xlog.debug("Visualizer closed.")
    
    def _prepare_animation_sizes(self):

        # Only the display areas that draw animations need their frames prepared (and cached on disk).
        # A size that was not prepared still works, but it is resized on demand and kept in memory only.
        display_areas_with_animations = self._xconfig.get("animations.display_areas", [DisplayArea.ANIMATIONS])

        animation_sizes_per_display_area = {}
        for display_area, rectangle in self.layout_info["relative"].items():
            if display_area not in display_areas_with_animations:
                continue

            # Calculate the size to draw the frame, based on the layout info and the size of the frame.
            width = rectangle.point_2.x - rectangle.point_1.x
            height = rectangle.point_2.y - rectangle.point_1.y

            # Also, we want to keep the aspect ratio of the original GIF, but resized to fit inside the given width and height.
            # Assuming here that:
            #   - The animation is squared
            # original_width, original_height = animation.frames[0].size
            aspect_ratio = 1.0
            if width / height > aspect_ratio:
                # We are limited by the height, we need to calculate the width based on the aspect ratio.
                desired_height_gif = height
                desired_width_gif = int(height * aspect_ratio)
            else:
                # We are limited by the width, we need to calculate the height based on the aspect ratio.
                desired_width_gif = width
                desired_height_gif = int(width / aspect_ratio)
            # Apply a final correction factor to make sure it fits into the display area, 
            # taking in account some padding and the rounded corners of the LCD.
            correction_factor = 0.8
            desired_width_gif = int(desired_width_gif * correction_factor)
            desired_height_gif = int(desired_height_gif * correction_factor)

            animation_sizes_per_display_area[display_area] = Size(desired_width_gif, desired_height_gif)

        return animation_sizes_per_display_area
    
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
            PaintObject(
                paints_by_queue={
                    PainterQueue.FOREGROUND: ForegroundPaint(
                        name="ArbitraryContentForegroundPaint",
                        command=ForegroundCommand(ForegroundCommand.ARBITRARY_TEXT_ICON),

                        drawing_callback=self.macros_foreground.draw_arbitrary_text_with_icon,
                        drawing_callback_parameters=params,

                        maintain_paint_for_seconds=params.get("for_seconds", self.DEFAULT_FOREGROUND_MAINTAIN_SECONDS),

                        # final_screen_clearing=True,
                        # remove_interaction_after_painting=True,
                        ignore_maintain_time=False
                    )
                }
            )
        )

    def arbitrary_text_while_speaking(self, params: dict):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.FOREGROUND: ForegroundPaint(
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
                }
            )
        )
    
    def arbitrary_text_while_thinking(self, params: dict):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.FOREGROUND: ForegroundPaint(
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
                }
            )
        )
    
    def arbitrary_text_while_idle(self, params: dict):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.FOREGROUND: ForegroundPaint(
                        name="ArbitraryContentWhileIdleForegroundPaint",
                        command=ForegroundCommand(ForegroundCommand.ARBITRARY_TEXT_ICON),

                        while_shared_memory_flag=SHARED_DSI_LCD_IDLE_MODE,
                        while_shared_memory_flag_value=True,

                        drawing_callback=self.macros_foreground.draw_arbitrary_text_with_icon,
                        drawing_callback_parameters=params,

                        maintain_paint_for_seconds=params.get("for_seconds", self.DEFAULT_FOREGROUND_MAINTAIN_SECONDS),

                        show_during_idle_mode=True,

                        # final_screen_clearing=True,
                        # remove_interaction_after_painting=True,
                        ignore_maintain_time=False,
                    ),
                    PainterQueue.ANIMATIONS: AnimationPaint(
                        name="IdleAnimationPaint",
                        command=AnimationsCommand(AnimationsCommand.IDLE),

                        while_shared_memory_flag=SHARED_DSI_LCD_IDLE_MODE,
                        while_shared_memory_flag_value=True,

                        # This sets the last iteration, so keep in mind that it counts starting from index `0`, so it is actually the total number of frames - 1.
                        loop_iterations=self.animations.get_animation("sleeping").get_frame_count() - 1,

                        maintain_paint_for_seconds=params.get("for_seconds", self.DEFAULT_FOREGROUND_MAINTAIN_SECONDS),
                        delay_between_frames=self.interaction_delays.get("idle", 0.1),

                        show_during_idle_mode=True,

                        drawing_callback=self.macros_background.merge_animation,
                        drawing_callback_parameters={**params, "animation": "sleeping"},
                        cache_control_parameters=["current_loop_iteration"],
                    )
                }
            )
        )
    
    def arbitrary_while_user_speaking(self, params: dict):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.FOREGROUND: ForegroundPaint(
                        name="ArbitraryContentWhileUserSpeakingForegroundPaint",
                        command=ForegroundCommand(ForegroundCommand.ARBITRARY_TEXT_ICON),

                        while_shared_memory_flag=SHARED_TRANSCRIBER_BUSY,
                        while_shared_memory_flag_value=True,

                        drawing_callback=self.macros_foreground.draw_arbitrary_text_with_icon,
                        drawing_callback_parameters=params,

                        maintain_paint_for_seconds=params.get("for_seconds", self.DEFAULT_FOREGROUND_MAINTAIN_SECONDS),

                        # final_screen_clearing=True,
                        # remove_interaction_after_painting=True,
                        ignore_maintain_time=False
                    )
                }
            )
        )
    
    def error(self, params: dict):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.FOREGROUND: ForegroundPaint(
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

                        maintain_paint_for_seconds=params.get("for_seconds", self.DEFAULT_FOREGROUND_MAINTAIN_SECONDS),

                        # final_screen_clearing=True,
                        # remove_interaction_after_painting=True,
                        ignore_maintain_time=False
                    )
                }
            )
        )
    
    def startup_initial(self, params: dict):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.FOREGROUND: ForegroundPaint(
                        name=f"StartupInitialForegroundPaint",
                        command=ForegroundCommand(ForegroundCommand.STARTUP),

                        drawing_callback=self.macros_foreground.draw_startup,
                        drawing_callback_parameters=params,

                        maintain_paint_for_seconds=self.interaction_delays.get("startup_splash", self.DEFAULT_FOREGROUND_MAINTAIN_SECONDS),

                        # final_screen_clearing=True,
                        # remove_interaction_after_painting=False,
                    )
                }
            )
        )
    
    def startup_with_phase(self, params: dict):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.FOREGROUND: ForegroundPaint(
                        name=f"StartupWithPhaseForegroundPaint",
                        command=ForegroundCommand(ForegroundCommand.STARTUP_WITH_PHASE),

                        drawing_callback=self.macros_foreground.draw_startup,
                        drawing_callback_parameters=params,
                        # cache_control_parameters=["phase"],

                        # final_screen_clearing=True,
                        # remove_interaction_after_painting=False,
                        overwrite_current_interaction_with_same_type = True,
                    ),
                    PainterQueue.STATUS: StatusPaint(
                        name=f"StartupWithPhaseStatusPaint",
                        command=StatusCommand(StatusCommand.STARTUP_WITH_PHASE),

                        drawing_callback=self.macros_status.draw_combined_init_phase,
                        drawing_callback_parameters=params,
                        cache_control_parameters=["phase"],

                        # ⚠️ When it gets removed after the time, a full clear is performed.
                        # TODO: THIS NEEDS TO BE FIXED, BECAUSE IT CAUSES A FLICKER WHEN THE PHASES ARE CHANGING, AND ALSO IT CAN CAUSE PROBLEMS IF WE WANT TO KEEP THE STATUS PAINTED AFTER THE STARTUP PHASES.
                        # It has to do with the hack for the idle mode. 
                        # What should happen is that there is a specific parameter to clean after removing 
                        #   due to the maintain_paint_for_seconds, or challenge the current approach for 
                        #   final_screen_clearing_needed and final_area_clearing_needed
                        # maintain_paint_for_seconds=params.get("for_seconds", self.DEFAULT_FOREGROUND_MAINTAIN_SECONDS),

                        # final_screen_clearing=True,
                        # remove_interaction_after_painting=False,
                        overwrite_current_interaction_with_same_type = True,
                    )
                }
            )
        )
    
    # ---- OVERALL PAINTS ----
    
    def code_block(self, params: dict):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.OVERALL: OverallPaint(
                        name="CodeBlockOverallPaint",
                        command=OverallCommand(OverallCommand.CODE_BLOCK),

                        drawing_callback=self.macros_overlay.draw_code_block,
                        drawing_callback_parameters={
                            "text": params.get("text", ""),
                            # "font_size": params.get("font_size", 20),
                            # "padding": params.get("padding", 5)
                        },

                        maintain_paint_for_seconds=params.get("for_seconds", self.DEFAULT_FOREGROUND_MAINTAIN_SECONDS),

                        # final_screen_clearing=True,
                        # remove_interaction_after_painting=True,
                        ignore_maintain_time=False
                    )
                }
            )
        )
    
    def code_block_while_speaking(self, params: dict):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.OVERALL: OverallPaint(
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
                }
            )
        )
    
    def text_block(self, params: dict):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.OVERALL: OverallPaint(
                        name="TextBlockOverallPaint",
                        command=OverallCommand(OverallCommand.TEXT_BLOCK),

                        drawing_callback=self.macros_overlay.draw_text_block,
                        drawing_callback_parameters={
                            "text": params.get("text", ""),
                            # "font_size": params.get("font_size", 20),
                            # "padding": params.get("padding", 5)
                        },

                        maintain_paint_for_seconds=params.get("for_seconds", self.DEFAULT_FOREGROUND_MAINTAIN_SECONDS),

                        # final_screen_clearing=True,
                        # remove_interaction_after_painting=True,
                        ignore_maintain_time=False
                    )
                }
            )
        )
    
    def text_block_while_speaking(self, params: dict):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.OVERALL: OverallPaint(
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
                }
            )
        )
    
    # ---- COMMON PAINTS ----

    def clear_foreground(self):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.FOREGROUND: ForegroundPaint(
                        name="ClearForegroundPaint",
                        command=ForegroundCommand(ForegroundCommand.CLEAR),

                    drawing_callback=self.macros_layout.base_frame_for_display_area,
                    drawing_callback_parameters={
                        "display_area": DisplayArea.MESSAGES,
                    },

                        # final_screen_clearing=False,
                        remove_interaction_after_painting=True
                    )
                }
            )
        )
    
    def clear_background(self):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.BACKGROUND: BackgroundPaint(
                        name="ClearBackgroundPaint",
                        command=BackgroundCommand(BackgroundCommand.CLEAR),

                        drawing_callback=self.macros_layout.base_frame_for_display_area,
                        drawing_callback_parameters={
                            "display_area": DisplayArea.BACKGROUND,
                        },

                        # final_screen_clearing=False,
                        remove_interaction_after_painting=True
                    )
                }
            )
        )

    def clear_animations(self):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.ANIMATIONS: BasePaint(
                        name="ClearAnimationsPaint",
                        command=AnimationsCommand(AnimationsCommand.CLEAR),

                        drawing_callback=self.macros_layout.base_frame_for_display_area,
                        drawing_callback_parameters={
                            "display_area": DisplayArea.ANIMATIONS,
                        },

                        remove_interaction_after_painting=True
                    )
                }
            )
        )

    # ---- BACKGROUND PAINTS ----

    def _speaking_animation_follows_audio(self) -> bool:
        """
        The speaking animation can follow the level of the audio being played (VU meter) instead of looping on a timer.
        Config: text-to-speech.speaking_animation = loop | vu. A mocked TTS has no audio to follow, so it always loops.
        """
        return self._xconfig.get("text-to-speech.speaking_animation", "loop") == "vu" \
            and not self._xconfig.get("text-to-speech.mock", True)

    def _speaker_level_provider(self) -> callable:
        """
        Builds the callable the painter evaluates on every iteration to get the speaker level,
        quantized to 0-4 (the mouth frames), so it can be used as a cache key.
        The shared memory values are attached lazily, once, the first time the level is read.
        """
        shared_memory = self.painter.get_painter_shared_memory().get_shared_memory_manager()
        attached = {"done": False}
        last = {"frame": None, "time": time.monotonic()}

        def provider() -> int:
            if not attached["done"]:
                shared_memory.attach_shared_memory_values_if_needed()
                attached["done"] = True
            level = shared_memory.read_shared_memory_value(SHARED_SPEAKER_LEVEL) or 0.0
            frame = max(0, min(4, round(level * 4)))
            # Tuning aid: only logs when the frame changes, with the time since the previous change.
            if frame != last["frame"]:
                now = time.monotonic()
                self._log_debug(f"Speaker level read by the painter: frame {last['frame']} -> {frame} "
                                f"(raw {level:.2f}, {now - last['time']:.3f}s since last change)")
                last["frame"], last["time"] = frame, now
            return frame

        return provider

    def speaking(self):

        follows_audio = self._speaking_animation_follows_audio()
        if follows_audio:
            # The level is read live on every painting iteration. Only 5 different images, so the cache does the work.
            drawing_callback = self.macros_background.draw_speaking_level
            cache_control_parameters = ["speaker_level"]
            dynamic_parameters = {"speaker_level": self._speaker_level_provider()}
        else:
            # The parameters on this call are added during the painting stage.
            #   - current_loop_iteration
            #   - max_loop_iterations
            # They are used by the macro method to calculate the phase to draw.
            drawing_callback = self.macros_background.draw_speaking_effect
            cache_control_parameters = ["current_loop_iteration"]
            dynamic_parameters = {}

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.BACKGROUND: BackgroundPaint(
                        name="SpeakingBackgroundPaint",
                        command=BackgroundCommand(BackgroundCommand.SPEAKING),

                        while_shared_memory_flag=SHARED_SPEAKER_BUSY,
                        while_shared_memory_flag_value=True,

                        drawing_callback=drawing_callback,
                        drawing_callback_parameters={},
                        cache_control_parameters=cache_control_parameters,
                        dynamic_parameters=dynamic_parameters,

                        loop_iterations=8,
                        delay_between_frames=self.interaction_delays.get("speaking", 
                                                                        self.interaction_delays.get("default_delay_between_frames", 
                                                                                                    0.05)),

                        final_area_clearing=True,
                        remove_interaction_after_painting=False

                        # TODO: Maybe we should do a soft clear after removing the interaction, 
                        # to avoid the persistence of the last phase of the effect on the screen, which can be a bit weird.
                    )
                }
            )
        )
    
    def thinking(self):
        """
        Shows that the chatbot is thinking, while the chatbot busy flag is on.
        The effect is an animation in the top left, chosen per display: `<display>.effects.thinking`
        is the name of one of the animations of `animations.map`.
        """

        animation_name = self._xconfig.get(f"{self.canvas.DEVICE_CONFIG_PREFIX}.effects.thinking", "thinking")

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.ANIMATIONS: AnimationPaint(
                        name="AnimationWhileThinkingAnimationPaint",
                        command=AnimationsCommand(AnimationsCommand.THINKING),

                        while_shared_memory_flag=SHARED_CHATBOT_BUSY,
                        while_shared_memory_flag_value=True,

                        # This sets the last iteration, so keep in mind that it counts starting from index `0`, so it is actually the total number of frames - 1.
                        loop_iterations=self.animations.get_animation(animation_name).get_frame_count() - 1,
                        delay_between_frames=self.interaction_delays.get("thinking", 
                                                                        self.interaction_delays.get("default_delay_between_frames", 
                                                                                                    0.05)),

                        # The parameter "current_loop_iteration" is added during the painting stage,
                        # and it is the index of the frame to draw.
                        drawing_callback=self.macros_background.merge_animation,
                        drawing_callback_parameters={"animation": animation_name},
                        cache_control_parameters=["current_loop_iteration"],

                        final_area_clearing=True,
                        remove_interaction_after_painting=False
                    )
                }
            )
        )
    
    def networking(self):
        """
        Shows that the network is busy, while the network busy flag is on.
        The effect is the scanner in blue, in the center left.
        """

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.BACKGROUND: BackgroundPaint(
                        name="ScannerWhileNetworkingBackgroundPaint",
                        command=BackgroundCommand(BackgroundCommand.NETWORKING),

                        while_shared_memory_flag=SHARED_NETWORK_BUSY,
                        while_shared_memory_flag_value=True,

                        # The parameters "current_loop_iteration" and "max_loop_iterations" are added during the painting stage.
                        # They are used by the macro method to calculate the phase to draw.
                        drawing_callback=self.macros_background.draw_scanner_effect,
                        drawing_callback_parameters={"color": self.canvas.COLOR_BLUE},
                        cache_control_parameters=["current_loop_iteration"],

                        loop_iterations=16,
                        delay_between_frames=self.interaction_delays.get("networking",
                                                                        self.interaction_delays.get("default_delay_between_frames",
                                                                                                    0.05)),

                        final_area_clearing=True,
                        remove_interaction_after_painting=False
                    )
                }
            )
        )

    def holding_percentage(self, param: dict):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.BACKGROUND: BackgroundPaint(
                        name=f"HoldingPercentageBackgroundPaint",
                        command=BackgroundCommand(BackgroundCommand.HOLDER_PERCENTAGE),

                        drawing_callback=self.macros_background.draw_interaction_holding_percentage,
                        drawing_callback_parameters=param,
                        cache_control_parameters=["percentage"],

                        overwrite_current_interaction_with_same_type=True,

                        final_screen_clearing=False,
                        remove_interaction_after_painting=False
                    )
                }
            )
        )

    def holding_percentage_end(self):
        # Same name and command as the paint set by holding_percentage(), so the Painter can find it.
        self.painter.request_removal(
            BackgroundPaint(
                name="HoldingPercentageBackgroundPaint",
                command=BackgroundCommand(BackgroundCommand.HOLDER_PERCENTAGE),
            ),
            PainterQueue.BACKGROUND,
            blank_screen=True)
    
    # ----- Status paints -----

    def show_status_line(self, param: dict):

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    PainterQueue.STATUS: StatusPaint(
                        name=f"StatusLineStatusPaint",
                        command=StatusCommand(StatusCommand.STATUS_LINE), # We can use the code to identify the type of status paint, or we can also use different commands for different types of status paints.

                        drawing_callback=self.macros_status.draw_status_line,
                        drawing_callback_parameters=param,
                        cache_control_parameters=["entries"],

                        # Painting the area empty is just housekeeping: it must never wake up a screen
                        #   that is deliberately blank (the idle mode starting). It is shown at the next draw.
                        trigger_draw_when_blank=len(param.get("entries", [])) > 0,

                        overwrite_current_interaction_with_same_type=False,

                        final_screen_clearing=False,
                        remove_interaction_after_painting=False
                    )
                }
            )
        )

    # ----- Buttons paints -----

    def _setup_buttons_monitoring(self):
        """
        Registers, once and forever, the callbacks that refresh the buttons when any of the flags or values they depend on changes.
        - Flags: one callback per flag AND value, as the PainterSharedMemory only detects transitions to a given value.
        - Values: one callback that runs on any change.
        The callbacks do not carry the new state: they just ask for a refresh, that reads the real flags and values.
        Whatever is already there at startup triggers its callback once, so the first paint comes for free.
        """
        painter_shared_memory = self.painter.get_painter_shared_memory()
        for button in BUTTONS:

            # ⚠️ A plain function (with the default argument to bind the column), NOT a functools.partial:
            #   the Painter logs callback.__name__ on every loop iteration and a partial has none.
            def refresh(column: str = button.column):
                self.refresh_buttons(column)

            if button.flag is not None:
                for value in (True, False):
                    painter_shared_memory.set_callback_for_shared_memory_flag(
                        name=f"refresh_buttons_{button.name}_{value}",
                        shared_memory_flag=button.flag,
                        activation_value=value,
                        callback=refresh,
                        is_dependant=False)

            if button.kind == "value":
                for suffix, index in (("value", button.value), ("extra", button.extra_value)):
                    if index is None:
                        continue
                    painter_shared_memory.set_callback_for_shared_memory_value(
                        name=f"refresh_buttons_{button.name}_{suffix}",
                        shared_memory_value=index,
                        callback=refresh)

    def refresh_buttons(self, column: str):
        """
        Reads the current flags and values of the buttons in the column, and paints the column. Safe to call from any thread.
        """
        shared_memory = self.painter.get_painter_shared_memory().get_shared_memory_manager()
        shared_memory.attach_shared_memory_values_if_needed()

        buttons = []
        states = []
        for button in BUTTONS:
            if button.column != column:
                continue

            if button.kind == "value":
                raw_value = shared_memory.read_shared_memory_value(button.value)
                value = int(round(raw_value)) if raw_value is not None else -1
                raw_extra = shared_memory.read_shared_memory_value(button.extra_value) if button.extra_value is not None else None
                extra = int(round(raw_extra)) if raw_extra is not None else None
                label, color, active = button.render(value, extra, self._xconfig)
            else:
                label, color = button.label, button.color
                active = shared_memory.read_shared_memory_flag(button.flag) == button.active_value

            buttons.append({"slot": button.slot, "label": label, "color": color, "active": active})
            # Everything that is drawn goes into the cache key, so any visible change is repainted.
            states.append(f"{button.name}={label}/{color}/{int(active)}")

        self.painter.paint(
            PaintObject(
                paints_by_queue={
                    self.BUTTONS_COLUMN_TO_QUEUE[column]: ButtonsPaint(
                        name=f"Buttons{column.capitalize()}ButtonsPaint",
                        command=ButtonsCommand(ButtonsCommand.BUTTONS_PANEL),

                        drawing_callback=self.macros_buttons.draw_buttons_panel,
                        drawing_callback_parameters={
                            "display_area": COLUMN_TO_DISPLAY_AREA[column],
                            "buttons": buttons,
                            "states": "|".join(states),
                        },
                        cache_control_parameters=["states"],

                        # Same pattern as the holding percentage: a new state replaces the previous panel.
                        overwrite_current_interaction_with_same_type=True,
                        # Draw state changes also in idle mode. Painting never wakes the app up.
                        show_during_idle_mode=True,

                        final_screen_clearing=False,
                        remove_interaction_after_painting=False
                    )
                }
            )
        )
    