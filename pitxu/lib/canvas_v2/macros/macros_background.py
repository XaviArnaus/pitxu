from PIL import Image, ImageDraw

from pyxavi import Config, Dictionary

from pitxu.lib.canvas_v2.macros.macros_base import MacrosBase
from pitxu.lib.canvas_v2.macros.bars_geometry import BarsGeometry

from pitxu.lib.objects.size import Size
from pitxu.lib.canvas_v2.layout_info import DisplayArea

class MacrosBackground(MacrosBase):
    """
    Drawings that take place in the background, and the animations.

    - The effects (the KITT mouth while speaking, the scanner while networking and the countdown bar) are drawn in the
        "center-left" area, as rectangles. Their geometry is proportional to the area, see BarsGeometry.
    - The animations (the emojis) are drawn in the "top-left" area.

    The old LED-emulation shapes are kept in pitxu/lib/legacy/macros_background_led.py.
    """

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config, params: Dictionary):
        super(MacrosBackground, self).__init__(config, params)

        # What the effects look like. They are tuned in the config, under the center-left area of the layout.
        mouth_columns = int(self._xconfig.get("dsi_lcd.layout.center_left.mouth_columns", 3))
        mouth_column_gap = float(self._xconfig.get("dsi_lcd.layout.center_left.mouth_column_gap", 2.0))
        # In pixels. 0 for square corners.
        self.corner_radius: int = int(self._xconfig.get("dsi_lcd.layout.center_left.corner_radius", 1))

        self.bars: BarsGeometry = BarsGeometry(
            area=self.layout_info["relative"][DisplayArea.BACKGROUND],
            mouth_columns=mouth_columns,
            mouth_column_gap_ratio=mouth_column_gap)

        self.log_summary("Macros Background Initialization", [
            ("mouth_columns", self.bars.mouth_columns),
            ("mouth_column_gap", f"{self.bars.mouth_column_gap_ratio} margins"),
            ("margin", f"{self.bars.margin} pixels"),
            ("corner_radius", f"{self.corner_radius} pixels"),
        ])

        self._xlog.debug("Initialized MacrosBackground.")

    # ---- Helpers ----

    def _draw_rectangles(self, draw: ImageDraw.ImageDraw, rectangles: list[tuple[int, int, int, int]], color: tuple | int):
        for rectangle in rectangles:
            if self.corner_radius > 0:
                draw.rounded_rectangle(rectangle, radius=self.corner_radius, fill=color)
            else:
                draw.rectangle(rectangle, fill=color)

    @staticmethod
    def _dim(color: tuple | int, brightness: float) -> tuple | int:
        """ The color at the given brightness (0-1), over the black of the background. The transparency, if any, is kept. """
        if isinstance(color, tuple):
            return tuple(int(channel * brightness) for channel in color[:3]) + tuple(color[3:])
        if isinstance(color, int):
            return int(color * brightness)
        return color

    def _clear_area(self, draw: ImageDraw.ImageDraw):
        self.base_frame_for_display_area(draw=draw, params={"display_area": DisplayArea.BACKGROUND})

    # ---- The scanner (networking) ----

    def scanner_loop_iterations(self) -> int:
        """ How many frames the scanner has, to give to the paint as its loop iterations. """
        return len(self.bars.scanner_sequence)

    def draw_scanner_effect(self, draw: ImageDraw.ImageDraw, params: dict):
        """
        Draws the scanner: the same slabs as the countdown, with a lit head that goes from one side to the other and back,
        followed by two dimmer ones. It is meant to be called directly from the painting loop, so it can control
        which frame to draw based on the loop iteration counter.
        """
        step = params.get("current_loop_iteration", 0) % len(self.bars.scanner_sequence)
        color = params.get("color", None) or self.canvas.COLOR_BLUE

        self._clear_area(draw)
        for rectangle, brightness in self.bars.scanner_slabs(step):
            self._draw_rectangles(draw, [rectangle], self._dim(color, brightness))

    # ---- The mouth (speaking) ----

    def _draw_mouth(self, draw: ImageDraw.ImageDraw, level: int, lag_per_ring: int):
        self._clear_area(draw)
        self._draw_rectangles(draw, self.bars.mouth_lit_bars(level, lag_per_ring), self.canvas.COLOR_RED)

    def draw_speaking_effect(self, draw: ImageDraw.ImageDraw, params: dict):
        """
        Draws the speaking effect, based on the given loop iterations counter and max value: the mouth opens
        (levels 1 to 4) and closes (3 to 0), all the columns moving together.
        It is meant to be called directly from the painting loop, so it can control which frame to draw based on the loop iteration counter.
        """
        current_loop_iteration = params.get("current_loop_iteration", 0)
        max_loop_iterations = params.get("max_loop_iterations", 0)

        half = max(1, max_loop_iterations // 2)
        frame = current_loop_iteration % half
        if current_loop_iteration < half:
            self._log_debug(f"Painter Loop: Drawing Speaking Increase, frame [{frame}].")
            level = frame + 1
        else:
            self._log_debug(f"Painter Loop: Drawing Speaking Decrease, frame [{frame}].")
            level = 3 - frame
        self._draw_mouth(draw, level=level, lag_per_ring=0)

    def draw_speaking_level(self, draw: ImageDraw.ImageDraw, params: dict):
        """
        Draws the mouth following a live audio level (VU meter style), instead of looping on a timer.
        The parameter "speaker_level" is read on every painting iteration by the painter, and it is already
        the level to draw (an integer, quantized by the visualizer so it can also be used as cache key).
        It is the same mouth as the looping effect: 0 is closed, 4 is the widest.
        The columns on the outside are one level behind the next ones towards the center, so they don't all move the same way.
        """
        level = max(0, min(4, int(params.get("speaker_level", 0) or 0)))
        self._draw_mouth(draw, level=level, lag_per_ring=1)

    # ---- The countdown (holding percentage) ----

    def draw_interaction_holding_percentage(self, draw: ImageDraw.ImageDraw, params: dict):
        '''
        Draws on the given canvas a percentage bar indicating how much time is left
        for the user to hold the interaction (i.e., speak): squares lit from the left, in the middle of the area.

        Args:
            draw: The canvas to draw on.
            params: A dictionary containing the parameters for the drawing.
                - percentage: The percentage of time left (0-100).
        '''
        percentage = params.get("percentage", 0)

        self._clear_area(draw)
        self._draw_rectangles(draw, self.bars.countdown_lit_slabs(percentage), self.canvas.COLOR_RED)

    # ---- The animations ----

    def merge_animation(self, base_image: Image.Image, params: dict):
        '''
        Draws a GIF on the LCD canvas.

        Args:
            draw: The canvas to draw on.
            params: A dictionary containing the parameters for the drawing.
                - gif_path: The path to the GIF file to draw.
        '''
        current_loop_iteration = params.get("current_loop_iteration", 0)
        max_loop_iterations = params.get("max_loop_iterations", 0)
        animation_name = params.get("animation", None)

        # Before anything, draw the display_area frame.
        draw = ImageDraw.Draw(base_image)
        self.base_frame_for_display_area(draw=draw, params={"display_area": DisplayArea.ANIMATIONS})

        # Peek into the loaded animation.
        animation = self.animations.get_animation(animation_name) if self.animations is not None else None
        if animation is None:
            self._xlog.error(f"Animation '{animation_name}' not found.")
            return

        self._log_debug(f"Loaded GIF '{animation_name}' with {animation.get_frame_count()} frames. Picking index {current_loop_iteration}")

        # Calculate the size to draw the frame, based on the layout info and the size of the frame.
        width = self.layout_info["relative"][DisplayArea.ANIMATIONS].point_2.x - self.layout_info["relative"][DisplayArea.ANIMATIONS].point_1.x
        height = self.layout_info["relative"][DisplayArea.ANIMATIONS].point_2.y - self.layout_info["relative"][DisplayArea.ANIMATIONS].point_1.y

        # Also, we want to keep the aspect ratio of the original GIF, but resized to fit inside the given width and height.
        original_width, original_height = animation.get_original_size()
        aspect_ratio = (original_width / original_height)
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

        # Calculate which frame to show based on the current loop iteration and max loop iterations
        frame_to_show = self.animations.get_animation_frame(
            animation_name, 
            current_loop_iteration, 
            desired_size=Size(width=desired_width_gif, height=desired_height_gif))

        # Calculate the position to draw the frame, centered in the display area.
        offset_x = self.layout_info["relative"][DisplayArea.ANIMATIONS].point_1.x + ((width - desired_width_gif) // 2)
        offset_y = self.layout_info["relative"][DisplayArea.ANIMATIONS].point_1.y + ((height - desired_height_gif) // 2)

        # Paint the frame on the canvas, resizing it to fit into the display area if needed.
        base_image.paste(frame_to_show, (offset_x, offset_y))