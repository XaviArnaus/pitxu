from PIL import ImageDraw

from pyxavi import Config, Dictionary
from pitxu.lib.objects import Point

from pitxu.lib.canvas_v2.macros_base import MacrosBase

class MacrosOverlay(MacrosBase):
    """
    Class to draw arbitrary things over the whole screen, not following the layout.
    At the beginning, it includes the Text and Code blocks, that are painted full screen over all the layout,
    with an own layout itself.
    """

    def __init__(self, config: Config, params: Dictionary):
        super(MacrosOverlay, self).__init__(config, params)

        self._xlog.debug("Initialized MacrosOverlay.")
    
    def draw_code_block(self, draw: ImageDraw.ImageDraw, params: dict):
        """
        Draws a full screen code block, with the biggest font that fits in width, and centered in the remaining space if it does not fill all the height.
        Does not follow the layout, it's an overlay over the whole screen, with a padding from the borders.
        """
        text = params.get("text", "")
        text_color = params.get("text_color", self.canvas.COLOR_BLACK)

        # Initial Background Paint clear
        self.base_frame_for_display_area(draw=draw, params={"display_area": "full_screen"})

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
        self.base_frame_for_display_area(draw=draw, params={"display_area": "full_screen"})

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