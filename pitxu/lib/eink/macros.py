from PIL import Image,ImageDraw,ImageFont

from pyxavi import Config, Logger, Dictionary
from . import EinkDisplay
from ..dto import Rectangle, Line, Point

import logging

class Macros:

    _config: Config = None
    _logger: logging = None
    _parameters: Dictionary = None

    _display_size: Point = None

    DEFAULT_STROKE: int = 1
    COLOR_BLACK: int = 0
    COLOR_WHITE: int = 1

    def __init__(self, config: Config, params: Dictionary):
        self._parameters = params
        self._config = config
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()
        self._display_size = Point(self._config.get("display.size.x"), self._config.get("display.size.y"))

    def draw_text_bubble(self, display: EinkDisplay, text: str, font: ImageFont):

        # First create a canvas
        canvas = display.create_canvas(reset_base_image=True)

        # Padding of text from bubble frame
        padding = 5

        # Drawing the frame, The bubble takes almost full screen
        # All coordinates are relative to these points
        rect_1 = Point(2, 2)
        rect_2 = Point(self._display_size.x - 2, self._display_size.y - 20)
        canvas.rounded_rectangle(
            Rectangle(rect_1, rect_2).to_image_rectangle(),
            radius=10,
            outline=self.COLOR_BLACK,
            fill=self.COLOR_WHITE,
            corners=(True, True, True, True))

        # Prepare the area for the text
        rect_text_1 = Point(rect_1.x + padding, rect_1.y + padding)
        rect_text_2 = Point(rect_2.x - padding - 2, rect_2.y - padding)
        textbox_boundaries = Rectangle(rect_text_1, rect_text_2)

        # Ensure that the text fits in the square.
        # For that, introduce line breaks in the text.
        # For now, do not care about overflowing vertically
        text = self.break_line_in_text_if_needed(canvas, text, textbox_boundaries, font)

        # Draw the text
        bounding_rectangle = canvas.multiline_text(rect_text_1.to_image_point(), text, font = font, fill = self.COLOR_BLACK)

        # The pick of the speach bubble
        canvas.line(Line(Point(30,rect_2.y), Point(40, rect_2.y)).to_image_line(), fill=self.COLOR_WHITE, width=1)
        canvas.line(Line(Point(30,rect_2.y), Point(31, self._display_size.y - 2)).to_image_line(), fill=self.COLOR_BLACK, width=1)
        canvas.line(Line(Point(31, self._display_size.y - 2), Point(40, rect_2.y)).to_image_line(), fill=self.COLOR_BLACK, width=1)

        # Now display the canvas
        display.display()

    def break_line_in_text_if_needed(self, canvas: ImageDraw, text: str, boundaries: Rectangle, font: ImageFont) -> str:

        self._logger.debug("Boundary left for text is " + "{:d}".format(boundaries.point_2.x))
        
        # Split the lines, we need to cover all individually
        lines = text.split("\n")
        words_to_add__to_next_line = []
        new_text_lines = []
        for line in lines:
            # First we add the words that don't have a space in the previous line
            words_to_add__to_next_line.reverse()
            working_line = " ".join(words_to_add__to_next_line) + (" " if words_to_add__to_next_line else "") + line
            words_to_add__to_next_line = []
            # What's the current size
            width_text = canvas.textlength(working_line, font)
            self._logger.debug("Line [" + working_line + "] has width " + "{:.9f}".format(width_text))
            # Loop while  the text is still bigger
            while(width_text > boundaries.point_2.x):
                # Split by words
                words = working_line.split(" ")
                # Join all but the last word
                working_line = " ".join(words[0:-1])
                # Keep the last word for the next line
                words_to_add__to_next_line.append(words[-1])
                # Get the new line size for the loop to analyse
                width_text = canvas.textlength(working_line, font)
            # Once the line is ready, add it to the outcome list
            new_text_lines.append(working_line)
        
        words_to_add__to_next_line.reverse()
        final_text = "\n".join(new_text_lines) + "\n" + " ".join(words_to_add__to_next_line)
        self._logger.debug("Final text is [" + final_text.replace("\n", "\\n") + "]")
        return final_text
    
    def startup_splash(self, display: EinkDisplay):

        # First create a canvas
        canvas = display.create_canvas(reset_base_image=True)

        # Main title
        title = self._config.get("app.name")
        version = self._parameters.get("app_version")
        canvas.text(Point(self._display_size.x / 2, self._display_size.y / 4).to_image_point(),
                    text = title + "  v" + version, 
                    font = display.FONT_BIG, 
                    fill = self.COLOR_BLACK,
                    anchor = "mm",
                    align = "center")
        
        # Draw a line between the title and the subtitle
        canvas.line(Rectangle(Point(5, self._display_size.y / 2), Point(self._display_size.x - 5, self._display_size.y / 2)).to_image_rectangle(),
                    fill = self.COLOR_BLACK,
                    width = 1)
        
        # Subtitle
        subtitle = "Chatbot: " + ("mocked" if self._config.get("chatbot.mock", True) else "real") + \
                    " | Display: " + ("mocked" if self._config.get("display.mock", True) else "real") + \
                    "\nSTT: " + ("mocked" if self._config.get("speech-to-text.mock", True) else "real") + \
                    " | TTS: " + ("mocked" if self._config.get("text-to-speech.mock", True) else "real")
        canvas.text(Point(self._display_size.x / 2, (self._display_size.y / 4) * 3).to_image_point(),
                    text = subtitle, 
                    font = display.FONT_MEDIUM, 
                    fill = self.COLOR_BLACK,
                    anchor = "mm",
                    align = "center")
        
        # Now display the canvas
        display.display()
        
    def ready_splash(self, display: EinkDisplay):
        # First create a canvas
        canvas = display.create_canvas(reset_base_image=True)

        # Show the Ready text
        canvas.text(Point(self._display_size.x / 2, self._display_size.y / 2).to_image_point(),
                    text = "Ready", 
                    font = display.FONT_BIG, 
                    fill = self.COLOR_BLACK,
                    anchor = "mm",
                    align = "center")
        
        # Now display the canvas
        display.display()