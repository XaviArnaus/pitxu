from PIL import Image,ImageDraw,ImageFont

from pyxavi.config import Config
from dto.rectangle import Rectangle, OffsetRectangle
from dto.point import Point
from dto.font_size import FontSize

class Macros:

    _config: Config = None
    _display_size: Point = None

    DEFAULT_STROKE: int = 1
    DEFAULT_OUTLINE: int = 1
    DEFAULT_FILL: int = 0

    def __init__(self, config: Config):
        self._config = config
        self._display_size = Point(self._config.get("display.size.x"), self._config.get("display.size.y"))

    def draw_text_bubble(self, canvas: ImageDraw, text: str, font_size: FontSize = FontSize.MEDIUM):

        # Padding of text from bubble frame
        padding = 3

        # Drawing the frame, The bubble takes almost full screen
        # All coordinates are relative to these points
        rect_1 = Point(2, 2)
        rect_2 = Point(self._display_size.x - 2, self._display_size.y - 10)
        canvas.rectangle(Rectangle(rect_1, rect_2).to_image_rectangle(),outline = self.DEFAULT_OUTLINE)

        # Prepare the area for the text
        rect_text_1 = Point(rect_1.x + padding, rect_1.y + padding)
        rect_text_2 = Point(rect_2.x - padding, rect_2.y - padding)

        # Ensure that the text fits in the square.
        # For that, introduce line breaks in the text.
        # For now, do not care about overflowing vertically
        #  .... it is really needed?

        # Draw the text
        canvas.multiline_text(Point(rect_text_1).to_image_point(), text, font = font_size, fill = 0)
