import logging
import os

from PIL import ImageDraw,ImageFont

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.canvas_v2.animations import Animations
from pitxu.lib.canvas_v2.markdown_renderer import MarkdownRenderer
from pitxu.lib.canvas_v2.painter.painter_timings import PainterTimings
from pitxu.lib.canvas_v2.layout_info import LayoutInfo, DisplayArea
from pitxu.lib.objects import Rectangle, Point
from pitxu.lib.canvas_v2.canvas import Canvas

class MacrosBase(PyXavi):
    """
    Base class for all the macros.
    """

    _display_size: Point = None
    _statics: dict[str, Canvas] = {
        "eyes_open": None,
        "eyes_closed": None
    }
    canvas: Canvas = None
    animations: Animations = None
    # Created on the first use, see get_markdown_renderer().
    _markdown_renderer: MarkdownRenderer = None

    layout_info: dict[str, dict[str, Rectangle]] = None
    color_scheme_info: dict[str, dict[str, any]] = None

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config, params: Dictionary):
        super(MacrosBase, self).init_pyxavi(config=config, params=params)

        # We're supposed to receive a Canvas object in the params, initialized specifically for the intended device.
        if params.key_exists("canvas"):
            self.canvas = params.get("canvas")
            self._display_size = self.canvas.get_screen_size()
        else:
            self._xlog.error("No Canvas object received in params for Macros class")
        
        # We need the layout info class to gather sizes and colors.
        layout_info_class: LayoutInfo = None
        if params.key_exists("layout_info_class"):
            layout_info_class = params.get("layout_info_class")
        else:
            self._xlog.error("No layout info class received in params for Macros class")
        
        # Calculate the layout info. Make sure that the padding is consistent (it may need a refactor)
        self.layout_info = layout_info_class.get_layout_info(padding=10, corners_radius=10)
        # Get the color scheme info
        self.color_scheme_info = layout_info_class.get_color_scheme_info()
        # Load the animations, if any
        if params.key_exists("animations"):
            self.animations = params.get("animations")
        else:
            self.animations = None

    def get_canvas(self) -> Canvas:
        return self.canvas

    def get_markdown_renderer(self) -> MarkdownRenderer:
        """
        The renderer that fits text (Markdown or plain) in an area, with the fonts of the canvas.
        Created on the first use: it needs the fonts of the canvas, and nobody pays for it until the first text.
        """
        if self._markdown_renderer is None:
            mono_file = os.path.join(
                self._xconfig.get("fonts.path", Canvas.DEFAULT_FONT_PATH),
                self._xconfig.get("fonts.mono_filename", "Font.ttc"))
            # Same switch as the Painter loop: where the time of every block goes is logged when it is on.
            timings = PainterTimings(
                enabled=bool(self._xconfig.get("dsi_lcd.painter.timing_log", False)),
                log_callback=lambda title, lines: self.log_summary(title, lines, log_level=logging.INFO))
            with timings.measure("renderer_creation"):
                self._markdown_renderer = MarkdownRenderer(
                    fonts=[
                        self.canvas.FONT_TINY,
                        self.canvas.FONT_SMALL,
                        self.canvas.FONT_MEDIUM,
                        self.canvas.FONT_BIG,
                        self.canvas.FONT_HUGE
                    ],
                    mono_font_file=mono_file,
                    mono_font_index=int(self._xconfig.get("fonts.mono_index", 1)),
                    color_mode=self.canvas.COLOR_MODE,
                    timings=timings)
        return self._markdown_renderer

    def get_display_size(self) -> Point:
        return self._display_size

    def wrap_text_to_lines(
            self, canvas: ImageDraw.ImageDraw, text: str, max_width, font: ImageFont, hard_split: bool = False) -> list[str]:
        """
        Wraps a text, greedily filling each line with words up to max_width.
        The line breaks already in the text are respected.

        Args:
            hard_split (bool): A word that is wider than max_width (a URL, say) is split in pieces
                that fit. When False, such a word stays whole in its own line and overflows.

        Returns:
            list[str]: The wrapped lines.
        """
        outcome: list[str] = []
        for line in text.split("\n"):
            if canvas.textlength(line, font) <= max_width:
                outcome.append(line)
                continue

            current_line = ""
            for word in line.split():
                if hard_split:
                    while canvas.textlength(word, font) > max_width and len(word) > 1:
                        fit = len(word) - 1
                        while fit > 1 and canvas.textlength(word[:fit], font) > max_width:
                            fit -= 1
                        if current_line != "":
                            outcome.append(current_line)
                            current_line = ""
                        outcome.append(word[:fit])
                        word = word[fit:]

                test_line = current_line + (" " if current_line != "" else "") + word
                if canvas.textlength(test_line, font) <= max_width:
                    current_line = test_line
                else:
                    if current_line != "":
                        outcome.append(current_line)
                    current_line = word
            outcome.append(current_line)
        return outcome

    def wrap_text_if_needed(self, canvas: ImageDraw.ImageDraw, text: str, max_width, font: ImageFont) -> str:
        try:
            lines = text.split("\n")
            longest_line = max(lines, key=lambda line: canvas.textlength(line, font=font))
            if canvas.textlength(longest_line, font) <= max_width:
                return text
            # Something overflows: wrap, each line ending in a line break.
            return "".join(line + "\n" for line in self.wrap_text_to_lines(canvas, text, max_width, font))
        except ValueError as e:
            self._xlog.error(f"Error wrapping text [{text}]: {e}")
            return text

    def base_frame_for_display_area(self, draw: ImageDraw.ImageDraw, params: dict[str, any]):
        '''
        

        Note about coordinates: There is a draw object per display area, merged into the main image.
            That's why the coordinates are relative to the display area, not to the full screen.
        '''

        display_area = params.get("display_area", DisplayArea.OVERALL)
        
        # Set the default, which is non-RGBA.
        outline = params.get("color", self.canvas.COLOR_BACKGROUND)
        fill = params.get("color", self.canvas.COLOR_BACKGROUND)
        rectangle: Rectangle = None
        
        if display_area in self.layout_info["relative"]:
            rectangle = self.layout_info["relative"][display_area]
            outline = self.color_scheme_info[display_area]["outline"]
            fill = self.color_scheme_info[display_area]["fill"]

            if self.canvas.COLOR_MODE == "RGBA":
                # And now the actual rectangle with the intended color and transparency.
                draw.rounded_rectangle(
                    rectangle.to_image_rectangle(),
                    radius=self.layout_info["params"]["corners_radius"],
                    outline=outline,
                    fill=fill,
                    corners=(True, True, True, True))
            else:
                draw.rectangle(
                    rectangle.to_image_rectangle(),
                    outline=outline,
                    fill=fill)
            
        else:
            self._xlog.warning(f"Unrecognized display area [{display_area}] for soft clear.")
            return
            
    
    def soft_full_clear(self, draw: ImageDraw.ImageDraw, params: dict[str, any]):
        '''
        Draws a rectangle over the given canvas.
        '''

        outline = params.get("color", self.canvas.COLOR_BACKGROUND)
        fill = params.get("color", self.canvas.COLOR_BACKGROUND)
        offset_x = 0
        offset_y = 0
        max_x = self._display_size.x
        max_y = self._display_size.y
        rectangle = Rectangle(Point(offset_x, offset_y), Point(max_x, max_y))

        draw.rectangle(
            rectangle.to_image_rectangle(),
            outline=outline,
            fill=fill)
    
    # def soft_display_area_clear(self, draw: ImageDraw.ImageDraw, params: dict[str, any]):
    #     '''
    #     Draws a rectangle over the given canvas.
    #     '''

    #     display_area = params.get("display_area", DisplayArea.OVERALL)

    #     if display_area in self.layout_info["relative"]:
    #         rectangle = self.layout_info["relative"][display_area]
    #         outline = self.canvas.COLOR_BACKGROUND
    #         fill = self.canvas.COLOR_BACKGROUND

    #         draw.rectangle(
    #             rectangle.to_image_rectangle(),
    #             outline=outline,
    #             fill=fill)