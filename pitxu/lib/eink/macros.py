from PIL import ImageDraw,ImageFont, ImageText

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary
from . import EinkDisplay
from ..objects import Rectangle, Line, Point

from pyxavi import dd

import logging

class Macros:

    _xconfig: Config = None
    _xlog: logging = None
    _xparams: Dictionary = None

    _display_size: Point = None
    _statics: dict[str, EinkDisplay] = {
        # "initial_eyes": None,
        "eyes_open": None,
        "eyes_closed": None
    }

    def __init__(self, config: Config, params: Dictionary):
        self._xparams = params
        self._xconfig = config
        self._xlog = Logger(config=config, base_path=self._xparams.get("base_path", "")).get_logger()
        self._display_size = Point(self._xconfig.get("display.size.x"), self._xconfig.get("display.size.y"))
    
    def load_or_create_statics(self,):
        '''
        Loads or creates the static images used in the macros.
        Currently, only the eyes images.

        It is meant to be called once at the initialization of the Display process,
        to have access to the singleton working image.
        '''
        # if self._statics["initial_eyes"] is None:
        #     self._xlog.info("Creating static image for initial eyes")
        #     display = EinkDisplay(config=self._xconfig, params=self._xparams)
        #     self._statics["initial_eyes"] = self._draw_initial_eyes(display)

        if self._statics["eyes_open"] is None:
            self._xlog.info("Creating static image for eyes open")
            display = EinkDisplay(config=self._xconfig, params=self._xparams)
            self._statics["eyes_open"] = self._draw_eyes_open(display)

        if self._statics["eyes_closed"] is None:
            self._xlog.info("Creating static image for eyes closed")
            display = EinkDisplay(config=self._xconfig, params=self._xparams)
            self._statics["eyes_closed"] = self._draw_eyes_closed(display)
    
    def get_display_size(self) -> Point:
        return self._display_size

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
            outline=display.COLOR_BLACK,
            fill=display.COLOR_WHITE,
            corners=(True, True, True, True))

        # Ensure that the text fits in the square.
        # For that, introduce line breaks in the text.
        # For now, do not care about overflowing vertically
        text = self.wrap_text_if_needed(canvas, text, rect_2.x - padding - 2, font)

        # Draw the text
        _bounding_rectangle = canvas.multiline_text(
            Point(rect_1.x + padding, rect_1.y + padding).to_image_point(), 
            text, 
            font = font, 
            fill = display.COLOR_BLACK)

        # The pick of the speach bubble
        canvas.line(Line(Point(30,rect_2.y), Point(40, rect_2.y)).to_image_line(), fill=display.COLOR_WHITE, width=1)
        canvas.line(Line(Point(30,rect_2.y), Point(31, self._display_size.y - 2)).to_image_line(), fill=display.COLOR_BLACK, width=1)
        canvas.line(Line(Point(31, self._display_size.y - 2), Point(40, rect_2.y)).to_image_line(), fill=display.COLOR_BLACK, width=1)

        # Now display the canvas
        display.display()
    
    def wrap_text_if_needed(self, canvas: ImageDraw.ImageDraw, text: str, max_width, font: ImageFont) -> str:
        width_text = canvas.textlength(text, font)
        if(width_text <= max_width):
            return text
        else:
            # Remove all possible current line breaks and then split by words
            words = text.replace("\n", " ").split(" ")
            new_text = ""
            current_line = ""
            
            for word in words:
                test_line = current_line + (" " if current_line != "" else "") + word
                width_test_line = canvas.textlength(test_line, font)
                if(width_test_line <= max_width):
                    current_line = test_line
                else:
                    new_text += current_line + "\n"
                    current_line = word
            new_text += current_line
            return new_text
    
    def startup_splash(self, display: EinkDisplay):

        # First create a canvas
        canvas = display.create_canvas(reset_base_image=True)

        # Main title
        title = self._xconfig.get("app.name")
        version = self._xparams.get("app_version")
        canvas.text(Point(self._display_size.x / 2, self._display_size.y / 4).to_image_point(),
                    text = title + "  v" + version, 
                    font = display.FONT_BIG, 
                    fill = display.COLOR_BLACK,
                    anchor = "mm",
                    align = "center")
        
        # Draw a line between the title and the subtitle
        canvas.line(Rectangle(Point(5, self._display_size.y / 2), Point(self._display_size.x - 5, self._display_size.y / 2)).to_image_rectangle(),
                    fill = display.COLOR_BLACK,
                    width = 1)
        
        # Subtitle
        subtitle = "Chatbot: " + ("mocked" if self._xconfig.get("chatbot.mock", True) else "real") + \
                    " | Display: " + ("mocked" if self._xconfig.get("display.mock", True) else "real") + \
                    "\nSTT: " + ("mocked" if self._xconfig.get("speech-to-text.mock", True) else "real") + \
                    " | TTS: " + ("mocked" if self._xconfig.get("text-to-speech.mock", True) else "real")
        canvas.text(Point(self._display_size.x / 2, (self._display_size.y / 4) * 3).to_image_point(),
                    text = subtitle, 
                    font = display.FONT_MEDIUM, 
                    fill = display.COLOR_BLACK,
                    anchor = "mm",
                    align = "center")
        
        # Now display the canvas
        display.display()
        
    def ready_splash(self, display: EinkDisplay):
        '''
        Not used
        '''
        # First create a canvas
        canvas = display.create_canvas(reset_base_image=True)

        # Show the Ready text
        canvas.text(Point(self._display_size.x / 2, self._display_size.y / 2).to_image_point(),
                    text = "Ready", 
                    font = display.FONT_BIG, 
                    fill = display.COLOR_BLACK,
                    anchor = "mm",
                    align = "center")
        
        # Now display the canvas
        display.display(partial=False)
    
    def arbitrary_text_centered(self, display: EinkDisplay, text: str):

        canvas = display.create_canvas(reset_base_image=True)
        canvas.text(Point(self._display_size.x / 2, self._display_size.y / 2).to_image_point(),
                    text = text,
                    font = display.FONT_HUGE,
                    fill = display.COLOR_BLACK,
                    anchor = "mm",
                    align = "center")
        display.display(partial=True)

    def arbitrary_text_with_icon(
            self,
            display: EinkDisplay, 
            text: str = None, 
            icon: str = None, 
            font_size: int = 24, 
            header: str = None, 
            font_header_size: int = 32,
            padding = 5) -> str:

        canvas = display.create_canvas(reset_base_image=True)

        # calculate anchor points and emojis for header and text
        if header and text:
            header_anchor = Point(self._display_size.x / 2, self._display_size.y / 3)
            text_anchor = Point(self._display_size.x / 2, (self._display_size.y / 4) * 3)
            header_emoji = icon + " " if icon else ""
            text_emoji = ""
        elif header and not text:
            header_anchor = Point(self._display_size.x / 2, self._display_size.y / 2)
            header_emoji = icon + " " if icon else ""
        elif not header and text:
            text_anchor = Point(self._display_size.x / 2, self._display_size.y / 2)
            text_emoji = icon + " " if icon else ""

        if header:
            canvas.text(header_anchor.to_image_point(),
                text = f"{header_emoji}{header}",
                font = display.get_font_by_size(font_header_size),
                fill = display.COLOR_BLACK,
                anchor = "mm",
                align = "center")

        if text:
            font = display.get_font_by_size(font_size)
            padding = 5
            value = self.wrap_text_if_needed(
                canvas=canvas,
                text=f"{text_emoji}{text}",
                max_width=self._display_size.x - (2 * padding),
                font=font
            )
            canvas.multiline_text(text_anchor.to_image_point(),
                text = value,
                font = font,
                fill = display.COLOR_BLACK,
                anchor = "mm",
                align = "center")
        
        display.display()
        
    
    def eyes_open(self, display: EinkDisplay = None):
        """
        Draw the eyes OPEN on the display.

        It is meant to be used after initial_eyes() as this does not draw the eye arcs.
        It is a partial update.
        """

        if display is None:
            self._xlog.debug("👀 Displaying precomputed static image for eyes open")

            # Use the precomputed static image
            self._statics["eyes_open"].display(partial=True)
        else:
            self._xlog.debug("👀 Drawing eyes open on given display")

            # Draw the eyes open (as partial=True) on the given display
            display = self._draw_eyes_open(display)

            # Now display the canvas
            display.display(partial=True)
    
    def eyes_closed(self, display: EinkDisplay = None):
        """
        Draw the eyes CLOSED on the display.

        It is meant to be used after initial_eyes(), as blinking from eyes_open().
        It is a partial update.
        """

        if display is None:
            self._xlog.debug("👀 Displaying precomputed static image for eyes closed")

            # Use the precomputed static image
            self._statics["eyes_closed"].display(partial=True)
        else:
            self._xlog.debug("👀 Drawing eyes closed on given display")

            # Draw the eyes closed (as partial=True) on the given display
            display = self._draw_eyes_closed(display)

            # Now display the canvas
            display.display(partial=True)
    
    def _draw_eyes_open(self, display: EinkDisplay):
        """
        Creates the eyes OPEN on the given display.

        It is meant to be used after initial_eyes() as this does not draw the eye arcs.
        It is a partial update.
        """
        
        # First create a canvas
        #canvas = display.create_canvas(reset_base_image=True)
        canvas = display.create_canvas(reset_base_image=False)

        # Left eye arc
        canvas.arc([(30, 20), (100, 90)], start=180, end=0, fill=0, width=4)
        canvas.arc([(30, 20), (59, 115)], start=80, end=200, fill=0, width=4)
        canvas.line([(45, 114), (75, 114)], width=4)

        # Right eye arc
        canvas.arc([(150, 20), (220, 90)], start=180, end=0, fill=0, width=4)
        canvas.arc([(192, 20), (221, 115)], start=340, end=100, fill=0, width=4)
        canvas.line([(175, 114), (205, 114)], width=4)

        # Draw the black pupils
        canvas.ellipse((75, 75, 95, 105), fill=0)  # Left pupil
        canvas.ellipse((155, 75, 175, 105), fill=0)  # Right pupil

        # We don't display the canvas, we return the display object for further use
        return display
    
    def _draw_eyes_closed(self, display: EinkDisplay):
        """
        Creates the eyes CLOSED on the given display.

        It is meant to be used after initial_eyes(), as blinking from eyes_open().
        It is a partial update.
        """
        
        # First create a canvas
        # canvas = display.create_canvas(reset_base_image=True)
        canvas = display.create_canvas(reset_base_image=False)

        # Left eye arc
        canvas.arc([(30, 20), (100, 90)], start=180, end=0, fill=0, width=4)
        canvas.arc([(30, 20), (59, 115)], start=80, end=200, fill=0, width=4)
        canvas.line([(45, 114), (75, 114)], width=4)

        # Right eye arc
        canvas.arc([(150, 20), (220, 90)], start=180, end=0, fill=0, width=4)
        canvas.arc([(192, 20), (221, 115)], start=340, end=100, fill=0, width=4)
        canvas.line([(175, 114), (205, 114)], width=4)

        # Draw the black pupils
        canvas.ellipse([(75, 95), (95, 95)], fill=0)  # Left pupil
        canvas.ellipse([(155, 95), (175, 95)], fill=0)  # Right pupil

        # We don't display the canvas, we return the display object for further use
        return display
    
    def soft_clear(self, display: EinkDisplay):

        # First create a canvas
        canvas = display.create_canvas(reset_base_image=True)

        # Create a white rectancgle with the sizes of the screen
        rect_1 = Point(0, 0)
        rect_2 = Point(self._display_size.x, self._display_size.y)
        canvas.rectangle(
            Rectangle(rect_1, rect_2).to_image_rectangle(),
            outline=display.COLOR_WHITE,
            fill=display.COLOR_WHITE)

        # Now display the canvas
        display.display()