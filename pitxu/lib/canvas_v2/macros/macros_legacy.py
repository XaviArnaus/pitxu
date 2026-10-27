from PIL import ImageDraw, ImageFont

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.device import Device
from pitxu.lib.canvas_v2.canvas import Canvas
from pitxu.lib.objects import Point, Rectangle, Line

from pitxu.lib.canvas_v2.macros.macros_base import MacrosBase

class MacrosLegacy(MacrosBase):
    """
    Class that contain the legacy macros. They have been active at some point, but as we moved on to other displays
    they became unused, but still want to keep them around, as they were (maybe) good ideas.

    Be careful, as development evolves, the parameters here may not be updated and may not fit anymore.
    For starts, this class is not meant to be instantiated at all.
    """

    device: Device = None

    def __init__(self, config: Config, params: Dictionary):
        super(MacrosLegacy, self).__init__(config, params)

        # The device is display-dependant, so it should be provided by the display-dependant-xprocess class (dsi_lcd, ...).
        if params.key_exists("device"):
            self.device = params.get("device")

        else:
            raise ValueError("'device' parameter is required for Visualizer.")

        self._xlog.debug("Initialized MacrosLegacy.")
    
    def load_or_create_statics(self):
        '''
        Loads or creates the static images used in the macros.
        Currently, only the eyes images.

        It is meant to be called once at the initialization of the Display process,
        to have access to the singleton working image.
        '''
        if self._statics["eyes_open"] is None:
            self._xlog.info("Creating static image for eyes open")
            # The next line provokes an unwanted eInk refresh, but feels needed to have the correct working image
            # TODO: There has been changes, check if it's still the case.
            canvas = Canvas(config=self._xconfig, params=self._xparams)
            self._statics["eyes_open"] = self._draw_eyes_open(canvas)

        if self._statics["eyes_closed"] is None:
            self._xlog.info("Creating static image for eyes closed")
            # The next line provokes an unwanted eInk refresh, but feels needed to have the correct working image
            # TODO: There has been changes, check if it's still the case.
            canvas = Canvas(config=self._xconfig, params=self._xparams)
            self._statics["eyes_closed"] = self._draw_eyes_closed(canvas)
    
    def draw_text_bubble(self, text: str, font: ImageFont):

        # First create a canvas
        draw = self.canvas.create_canvas_over_new_image()

        # Padding of text from bubble frame
        padding = 5

        # Drawing the frame, The bubble takes almost full screen
        # All coordinates are relative to these points
        rect_1 = Point(2, 2)
        rect_2 = Point(self._display_size.x - 2, self._display_size.y - 20)
        draw.rounded_rectangle(
            Rectangle(rect_1, rect_2).to_image_rectangle(),
            radius=10,
            outline=self.canvas.COLOR_BLACK,
            fill=self.canvas.COLOR_WHITE,
            corners=(True, True, True, True))

        # Ensure that the text fits in the square.
        # For that, introduce line breaks in the text.
        # For now, do not care about overflowing vertically
        text = self.wrap_text_if_needed(draw, text, rect_2.x - padding - 2, font)

        # Draw the text
        _bounding_rectangle = draw.multiline_text(
            Point(rect_1.x + padding, rect_1.y + padding).to_image_point(), 
            text, 
            font = font, 
            fill = self.canvas.COLOR_BLACK)

        # The pick of the speach bubble
        draw.line(Line(Point(30,rect_2.y), Point(40, rect_2.y)).to_image_line(), fill=self.canvas.COLOR_WHITE, width=1)
        draw.line(Line(Point(30,rect_2.y), Point(31, self._display_size.y - 2)).to_image_line(), fill=self.canvas.COLOR_BLACK, width=1)
        draw.line(Line(Point(31, self._display_size.y - 2), Point(40, rect_2.y)).to_image_line(), fill=self.canvas.COLOR_BLACK, width=1)

        self.device.display(self.canvas.get_image())
    
    def eyes_open(self):
        """
        Draw the eyes OPEN on the display.

        It is meant to be used after initial_eyes() as this does not draw the eye arcs.
        It is a partial update.
        """

        if self._statics["eyes_open"] is None:
            self.load_or_create_statics()

        self.device.display(self._statics["eyes_open"].get_image(), partial=True)

    def eyes_closed(self):
        """
        Draw the eyes CLOSED on the display.

        It is meant to be used after initial_eyes(), as blinking from eyes_open().
        It is a partial update.
        """

        if self._statics["eyes_closed"] is None:
            self.load_or_create_statics()

        self.device.display(self._statics["eyes_closed"].get_image(), partial=True)

    def _draw_eyes_open(self, canvas: Canvas):
        """
        Creates the eyes OPEN on the given display.

        It is meant to be used after initial_eyes() as this does not draw the eye arcs.
        It is a partial update.
        """
        
        # First get a canvas
        draw = canvas.get_canvas(reset_base_image=False)

        # Left eye arc
        draw.arc([(30, 20), (100, 90)], start=180, end=0, fill=self.canvas.COLOR_FOREGROUND, width=4)
        draw.arc([(30, 20), (59, 115)], start=80, end=200, fill=self.canvas.COLOR_FOREGROUND, width=4)
        draw.line([(45, 114), (75, 114)], width=4)

        # Right eye arc
        draw.arc([(150, 20), (220, 90)], start=180, end=0, fill=self.canvas.COLOR_FOREGROUND, width=4)
        draw.arc([(192, 20), (221, 115)], start=340, end=100, fill=self.canvas.COLOR_FOREGROUND, width=4)
        draw.line([(175, 114), (205, 114)], width=4)

        # Draw the black pupils
        draw.ellipse((75, 75, 95, 105), fill=self.canvas.COLOR_FOREGROUND)  # Left pupil
        draw.ellipse((155, 75, 175, 105), fill=self.canvas.COLOR_FOREGROUND)  # Right pupil

        # Return the canvas with the drawn eyes
        return canvas
    
    def _draw_eyes_closed(self, canvas: Canvas):
        """
        Creates the eyes CLOSED on the given display.

        It is meant to be used after initial_eyes(), as blinking from eyes_open().
        It is a partial update.
        """
        
        # First get a canvas
        draw = canvas.get_canvas(reset_base_image=False)

        # Left eye arc
        draw.arc([(30, 20), (100, 90)], start=180, end=0, fill=self.canvas.COLOR_FOREGROUND, width=4)
        draw.arc([(30, 20), (59, 115)], start=80, end=200, fill=self.canvas.COLOR_FOREGROUND, width=4)
        draw.line([(45, 114), (75, 114)], width=4)

        # Right eye arc
        draw.arc([(150, 20), (220, 90)], start=180, end=0, fill=self.canvas.COLOR_FOREGROUND, width=4)
        draw.arc([(192, 20), (221, 115)], start=340, end=100, fill=self.canvas.COLOR_FOREGROUND, width=4)
        draw.line([(175, 114), (205, 114)], width=4)

        # Draw the black pupils
        draw.ellipse([(75, 95), (95, 95)], fill=self.canvas.COLOR_FOREGROUND)  # Left pupil
        draw.ellipse([(155, 95), (175, 95)], fill=self.canvas.COLOR_FOREGROUND)  # Right pupil

        # Return the canvas with the drawn eyes
        return canvas