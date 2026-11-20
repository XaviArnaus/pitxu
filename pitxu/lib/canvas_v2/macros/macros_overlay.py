import logging
import threading

from PIL import ImageDraw

from pyxavi import Config, Dictionary, full_stack
from pitxu.lib.objects import Point

from pitxu.lib.canvas_v2.macros.macros_base import MacrosBase
from pitxu.lib.canvas_v2.layout_info import DisplayArea
from pitxu.lib.utils import markdown_parser

class MacrosOverlay(MacrosBase):
    """
    Class to draw arbitrary things over the whole screen, not following the layout.
    At the beginning, it includes the Text and Code blocks, that are painted full screen over all the layout,
    with an own layout itself.

    The Text blocks are rendered as Markdown (bold, italic, inline code, code blocks, headings and lists),
    and the Code blocks in a monospaced font. If anything fails there, they fall back to the plain drawing.
    Config (all optional):
        - canvas.markdown.enabled: [Boolean] False to always use the plain drawing. Default True.
        - fonts.mono_filename: [String] Font file for the code, inside fonts.path. Default Font.ttc
        - fonts.mono_index: [Integer] Face inside the font file, for font collections. Default 1 (the mono face of Font.ttc)
    """

    # The padding of the content from the borders of the screen, like in the plain drawing.
    MARKDOWN_BOX_PADDING: int = 15

    # The renderer (see MacrosBase.get_markdown_renderer()) is shared by the warm-up thread and the Painter, and it is not meant for two at the same time.
    _markdown_lock: threading.RLock = None

    def __init__(self, config: Config, params: Dictionary):
        super(MacrosOverlay, self).__init__(config, params)

        # The Markdown parser logs a lot at DEBUG: INFO unless the config says otherwise.
        markdown_parser.set_log_level(self._xconfig.get("libs_logger.markdown_it.loglevel", logging.INFO))

        self._markdown_lock = threading.RLock()
        # The first block would pay for building the parser and loading fonts (it took 300 ms on the Pi): do it now, off the Painter.
        if self._xconfig.get("canvas.markdown.enabled", True) and self._xconfig.get("canvas.markdown.warm_up", True):
            threading.Thread(name="MarkdownWarmUp", target=self._warm_up_markdown, daemon=True).start()

        self._xlog.debug("Initialized MacrosOverlay.")

    def _warm_up_markdown(self):
        """ Runs in its own thread, at the start. A failure only means that the first block pays for it, as before. """
        try:
            with self._markdown_lock:
                self.get_markdown_renderer().warm_up()
            self._xlog.debug("Markdown renderer warmed up.")
        except Exception as e:
            self._xlog.warning(f"Could not warm up the Markdown renderer: {e}")

    def _draw_with_markdown_renderer(self, draw: ImageDraw.ImageDraw, text: str, text_color, is_code: bool) -> bool:
        """
        Tries to draw the text with the Markdown renderer. Returns False when it did not, so the caller draws the plain one.
        The frame is cleaned again if the renderer failed, so the plain drawing does not go over a half drawn one.
        """
        if not self._xconfig.get("canvas.markdown.enabled", True):
            return False

        box = (
            self.MARKDOWN_BOX_PADDING,
            self.MARKDOWN_BOX_PADDING,
            self._display_size.x - self.MARKDOWN_BOX_PADDING - 2,
            self._display_size.y - self.MARKDOWN_BOX_PADDING - 2)

        try:
            with self._markdown_lock:
                renderer = self.get_markdown_renderer()
                if is_code:
                    return renderer.draw_code(draw, text, box, text_color)
                return renderer.draw(draw, text, box, text_color)
        except Exception as e:
            self._xlog.warning(f"Could not render the {'code' if is_code else 'text'} block with the Markdown renderer, drawing it plain: {e}")
            self._xlog.debug(full_stack())
            self.base_frame_for_display_area(draw=draw, params={"display_area": DisplayArea.OVERALL})
            return False

    def draw_code_block(self, draw: ImageDraw.ImageDraw, params: dict):
        """
        Draws a full screen code block, with the biggest font that fits in width, and centered in the remaining space if it does not fill all the height.
        Does not follow the layout, it's an overlay over the whole screen, with a padding from the borders.
        """
        text = params.get("text", "")
        text_color = params.get("text_color", self.canvas.COLOR_BLACK)

        # Initial Background Paint clear
        self.base_frame_for_display_area(draw=draw, params={"display_area": DisplayArea.OVERALL})

        # In a monospaced font, preferring a smaller font over wrapping the lines.
        if self._draw_with_markdown_renderer(draw, text, text_color, is_code=True):
            return

        # Plain drawing, the fallback.
        padding_rectangle = 10
        padding_code_text = 5
        text_anchor_point = Point(padding_rectangle + padding_code_text, padding_rectangle + padding_code_text)
        max_lenght_width = self._display_size.x - (2 * padding_rectangle) - (2 * padding_code_text) - 2
        max_lenght_height = self._display_size.y - (2 * padding_rectangle) - (2 * padding_code_text) - 2

        # Calculate the best fitting font size
        possible_font_sizes = [
            self.canvas.FONT_TINY,
            self.canvas.FONT_SMALL,
            self.canvas.FONT_MEDIUM,
            self.canvas.FONT_BIG,
            self.canvas.FONT_HUGE
        ]

        code_text_font = None
        width_text = None
        heigh_text = None
        for possible_font in possible_font_sizes:
            possible_width_text = draw.multiline_textbbox(
                text_anchor_point.to_image_point(),
                text,
                font=possible_font,
                anchor="la",
                align="left")
            
            # it's a tuple of 4 positions: (x0, y0, x1, y1) where (x1 - x0) is the width of the text and (y1 - y0) is the height of the text.
            if(possible_width_text[2] - possible_width_text[0] <= max_lenght_width):
                code_text_font = possible_font
                width_text = possible_width_text[2] - possible_width_text[0]
                heigh_text = possible_width_text[3] - possible_width_text[1]
            else:
                break
        
        # At this point, the code_text_font is the biggest font that fits in width. If none fits, it will be the smallest one.
        if code_text_font is None:
            code_text_font = self.canvas.FONT_SMALL
            width_text = max_lenght_width
            heigh_text = max_lenght_height

        # If the text is actually small even for the biggest font, we can center it in the remaining space.
        if width_text < max_lenght_width:
            extra_space = max_lenght_width - width_text
            text_anchor_point.x += extra_space / 2  
        # Same for vertical
        if heigh_text < max_lenght_height:
            extra_space = max_lenght_height - heigh_text
            text_anchor_point.y += extra_space / 2
        
        # Ensure that the text fits in the square.
        # text = self.wrap_text_if_needed(draw, text, (self._display_size.x - (2 * padding_rectangle) - (2 * padding_code_text)) - 2, code_text_font)

        # Draw the text
        _bounding_rectangle = draw.multiline_text(
            text_anchor_point.to_image_point(), 
            text, 
            font = code_text_font, 
            fill = text_color,
            anchor = "la",
            align= "left")
    
    def draw_text_block(self, draw: ImageDraw.ImageDraw, params: dict):
        """
        Draws a full screen text block, with the biggest font that fits in width, and centered in the remaining space if it does not fill all the height.
        Does not follow the layout, it's an overlay over the whole screen, with a padding from the borders.
        """

        text = params.get("text", "")
        text_color = params.get("text_color", self.canvas.COLOR_BLACK)

        # Initial Background Paint clear
        self.base_frame_for_display_area(draw=draw, params={"display_area": DisplayArea.OVERALL})

        # Rendered as Markdown: bold, italic, inline code, code blocks, headings and lists.
        if self._draw_with_markdown_renderer(draw, text, text_color, is_code=False):
            return

        # Plain drawing, the fallback.
        padding_rectangle = 10
        padding_text = 5
        text_anchor_point = Point(padding_rectangle + padding_text, padding_rectangle + padding_text)
        max_lenght_width = self._display_size.x - (2 * padding_rectangle) - (2 * padding_text) - 2
        max_lenght_height = self._display_size.y - (2 * padding_rectangle) - (2 * padding_text) - 2

        # Calculate the best fitting font size
        possible_font_sizes = [
            self.canvas.FONT_TINY,
            self.canvas.FONT_SMALL,
            self.canvas.FONT_MEDIUM,
            self.canvas.FONT_BIG,
            self.canvas.FONT_HUGE
        ]

        text_font = None
        width_text = None
        heigh_text = None
        for possible_font in possible_font_sizes:
            possible_width_text = draw.multiline_textbbox(
                text_anchor_point.to_image_point(),
                text,
                font=possible_font,
                anchor="la",
                align="left")
            
            # it's a tuple of 4 positions: (x0, y0, x1, y1) where (x1 - x0) is the width of the text and (y1 - y0) is the height of the text.
            if(possible_width_text[2] - possible_width_text[0] <= max_lenght_width):
                text_font = possible_font
                width_text = possible_width_text[2] - possible_width_text[0]
                heigh_text = possible_width_text[3] - possible_width_text[1]
            else:
                break
        
        # At this point, the text_font is the biggest font that fits in width. If none fits, it will be the smallest one.
        if text_font is None:
            text_font = self.canvas.FONT_SMALL
            width_text = max_lenght_width
            heigh_text = max_lenght_height

        # If the text is actually small even for the biggest font, we can center it in the remaining space.
        if width_text < max_lenght_width:
            extra_space = max_lenght_width - width_text
            text_anchor_point.x += extra_space / 2  
        # Same for vertical
        if heigh_text < max_lenght_height:
            extra_space = max_lenght_height - heigh_text
            text_anchor_point.y += extra_space / 2
        
        # Ensure that the text fits in the square.
        text = self.wrap_text_if_needed(
            draw, 
            text, 
            (self._display_size.x - (2 * padding_rectangle) - (2 * padding_text)) - 2,
            text_font)

        # Draw the text
        _bounding_rectangle = draw.multiline_text(
            text_anchor_point.to_image_point(), 
            text, 
            font = text_font, 
            fill = text_color,
            anchor = "la",
            align= "left")