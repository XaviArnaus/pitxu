from PIL import ImageDraw,ImageFont

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.objects import Rectangle, Line, Point
from pitxu.lib.canvas.canvas import Canvas
from pitxu.lib.abstract.device import Device

import time, math


class Macros(PyXavi):

    _display_size: Point = None
    _statics: dict[str, Canvas] = {
        "eyes_open": None,
        "eyes_closed": None
    }
    canvas: Canvas = None
    device: Device = None

    LED_TO_LCD_OFFSET_X: int = 40  # Pixels to offset in X to avoid rounded corners

    def __init__(self, config: Config, params: Dictionary):
        super(Macros, self).init_pyxavi(config=config, params=params)

        # We're supposed to receive a Canvas object in the params, initialized specifically for the intended device.
        if params.key_exists("canvas"):
            self.canvas = params.get("canvas")
            self._display_size = self.canvas.get_screen_size()
        else:
            self._xlog.error("No Canvas object received in params for Macros class")
        
        # We're supposed to receive a Device object in the params, initialized specifically for the intended device.
        if params.key_exists("device"):
            self.device = params.get("device")
        else:
            self._xlog.error("No Device object received in params for Macros class")
        
        # self._display_size = Point(self._xconfig.get("eink.size.x"), self._xconfig.get("eink.size.y"))

    
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
    
    def get_display_size(self) -> Point:
        return self._display_size

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

    def wrap_text_if_needed(self, canvas: ImageDraw.ImageDraw, text: str, max_width, font: ImageFont) -> str:
        try:
            width_text = canvas.textlength(text.replace("\n", ""), font)
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
        except ValueError as e:
            self._xlog.error(f"Error wrapping text [{text}]: {e}")
            return text
    
    def startup_splash(self) -> ImageDraw.ImageDraw:

        # First create a canvas
        draw = self.canvas.create_canvas_over_new_image()

        # Main title
        title = self._xconfig.get("app.name")
        version = self._xparams.get("app_version")
        draw.text(Point(self._display_size.x / 2, self._display_size.y / 4).to_image_point(),
                    text = title + "  v" + version, 
                    font = self.canvas.FONT_BIG, 
                    fill = self.canvas.COLOR_BLACK,
                    anchor = "mm",
                    align = "center")
        
        # Draw a line between the title and the subtitle
        draw.line(Rectangle(Point(5, self._display_size.y / 2), Point(self._display_size.x - 5, self._display_size.y / 2)).to_image_rectangle(),
                    fill = self.canvas.COLOR_BLACK,
                    width = 1)
        
        # Subtitle
        subtitle = "Chatbot: " + ("mocked" if self._xconfig.get("chatbot.mock", True) else "real") + \
                    " | Display: " + ("mocked" if self._xconfig.get("eink.mock", True) else "real") + \
                    "\nSTT: " + ("mocked" if self._xconfig.get("speech-to-text.mock", True) else "real") + \
                    " | TTS: " + ("mocked" if self._xconfig.get("text-to-speech.mock", True) else "real")
        draw.text(Point(self._display_size.x / 2, (self._display_size.y / 4) * 3).to_image_point(),
                    text = subtitle, 
                    font = self.canvas.FONT_MEDIUM, 
                    fill = self.canvas.COLOR_BLACK,
                    anchor = "mm",
                    align = "center")
        
        # Flush the image (generated from the canvas) to the device
        self.device.display(self.canvas.get_image())

    def ready_splash(self) -> ImageDraw.ImageDraw:
        '''
        Not used
        '''
        # First create a canvas
        canvas = self.canvas.create_canvas_over_new_image()

        # Show the Ready text
        canvas.text(Point(self._display_size.x / 2, self._display_size.y / 2).to_image_point(),
                    text = "Ready", 
                    font = self.canvas.FONT_BIG, 
                    fill = self.canvas.COLOR_BLACK,
                    anchor = "mm",
                    align = "center")
        
        # Flush the image (generated from the canvas) to the device
        self.device.display(self.canvas.get_image())

    def arbitrary_text_centered(self, text: str) :

        canvas = self.canvas.create_canvas_over_new_image()
        canvas.text(Point(self._display_size.x / 2, self._display_size.y / 2).to_image_point(),
                    text = text,
                    font = self.canvas.FONT_HUGE,
                    fill = self.canvas.COLOR_BLACK,
                    anchor = "mm",
                    align = "center")
        self.device.display(self.canvas.get_image())

    def arbitrary_text_with_icon(
            self,
            text: str = None, 
            icon: str = None, 
            font_size: int = 24, 
            header: str = None, 
            font_header_size: int = 32,
            padding: int = 5) -> str:

        canvas = self.canvas.create_canvas_over_new_image()

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
                font = self.canvas.get_font_by_size(font_header_size),
                fill = self.canvas.COLOR_BLACK,
                anchor = "mm",
                align = "center")

        if text:
            font = self.canvas.get_font_by_size(font_size)
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
                fill = self.canvas.COLOR_BLACK,
                anchor = "mm",
                align = "center")
        
        # Flush the image (generated from the canvas) to the device
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
        draw.arc([(30, 20), (100, 90)], start=180, end=0, fill=0, width=4)
        draw.arc([(30, 20), (59, 115)], start=80, end=200, fill=0, width=4)
        draw.line([(45, 114), (75, 114)], width=4)

        # Right eye arc
        draw.arc([(150, 20), (220, 90)], start=180, end=0, fill=0, width=4)
        draw.arc([(192, 20), (221, 115)], start=340, end=100, fill=0, width=4)
        draw.line([(175, 114), (205, 114)], width=4)

        # Draw the black pupils
        draw.ellipse((75, 75, 95, 105), fill=0)  # Left pupil
        draw.ellipse((155, 75, 175, 105), fill=0)  # Right pupil

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
        draw.arc([(30, 20), (100, 90)], start=180, end=0, fill=0, width=4)
        draw.arc([(30, 20), (59, 115)], start=80, end=200, fill=0, width=4)
        draw.line([(45, 114), (75, 114)], width=4)

        # Right eye arc
        draw.arc([(150, 20), (220, 90)], start=180, end=0, fill=0, width=4)
        draw.arc([(192, 20), (221, 115)], start=340, end=100, fill=0, width=4)
        draw.line([(175, 114), (205, 114)], width=4)

        # Draw the black pupils
        draw.ellipse([(75, 95), (95, 95)], fill=0)  # Left pupil
        draw.ellipse([(155, 95), (175, 95)], fill=0)  # Right pupil

        # Return the canvas with the drawn eyes
        return canvas
    
    def soft_clear(self):

        # First create a canvas
        draw = self.canvas.get_canvas()

        # Create a background color rectangle with the sizes of the screen
        self._soft_clear_rectangle(draw=draw)

        # Flush the image (generated from the canvas) to the device
        self.device.display(self.canvas.get_image())

    def _soft_clear_rectangle(self, draw: ImageDraw.ImageDraw, color: str = None):
        '''
        Draws a rectangle over the given canvas.
        '''
        if color is None:
            color = self.canvas.COLOR_BLACK

        point_1 = Point(0, 0)
        point_2 = Point(self._display_size.x, self._display_size.y)
        draw.rectangle(
            Rectangle(point_1, point_2).to_image_rectangle(),
            outline=color,
            fill=color)
    
    # ------ Matrix Led effects adapted to LCD -------

    def kitt_horizontal_effect(self, delay: float = 0.1):
        self._log_debug("Starting KITT effect")

        draw = self.canvas.get_canvas(reset_base_image = False)
        self._soft_clear_rectangle(draw=draw)
        image = self.canvas.get_image()

        apply_offset = False

        # Move right
        for x in range(8):
            self._soft_clear_rectangle(draw=draw, color=self.canvas.COLOR_BLACK)
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 3), apply_offset=apply_offset)
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 4), apply_offset=apply_offset)
            self.device.display(image)
            time.sleep(delay)
        # Move left
        for x in range(6,-1,-1):
            self._soft_clear_rectangle(draw=draw, color=self.canvas.COLOR_BLACK)
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 3), apply_offset=apply_offset)
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 4), apply_offset=apply_offset)
            self.device.display(image)
            time.sleep(delay)
    
    def kitt_speaking_effect_vu_meter(self, col_1: int, col_2: int, col_3: int, col_4: int, delay: float = 0.03):
        '''
        KITT speaking effect using VU Meter columns

        Be careful, it relies on having a HandableCanvas instance opened previously, and
        needs to be closed afterwards.
        '''
        draw = self.canvas.get_canvas(reset_base_image = False)
        self._soft_clear_rectangle(draw=draw)
        # The "draw" object is linked to the canvas, so we can get the image from there
        # It gets updated as we draw on it, so is more efficient than getting it each time
        image = self.canvas.get_image()

        max_values = {
            # "col_1": col_1,
            "col_2": col_2,
            "col_3": col_3,
            "col_4": col_4,
        }

        apply_offset = False

        # We go row by row from the middle point to the top and bottom extremes
        for y in range(0, 4):

            # We go through each column to see if we need to light it at this row
            for col_key, col_value in max_values.items():
                if col_value > y:
                    # We just skip the lowest one
                    # if col_key == "col_1":
                    #     # Column 1 and 7
                    #     canvas.point((0, 3 - y), self.ON)
                    #     canvas.point((0, 4 + y), self.ON)
                    #     canvas.point((7, 3 - y), self.ON)
                    #     canvas.point((7, 4 + y), self.ON)
                    # Removing the second lowest to give a separation space betweem 3 and 4
                    # if col_key == "col_2":
                    #     # Column 1 and 8
                    #     canvas.point((0, 3 - y), self.ON)
                    #     canvas.point((0, 4 + y), self.ON)
                    #     canvas.point((7, 3 - y), self.ON)
                    #     canvas.point((7, 4 + y), self.ON)
                    if col_key == "col_3":
                        # Column 2, 3 (left, -1 for a separation column), 6 and 7 (right, +1 for a separation column)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(0, 3 - y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(0, 4 + y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(1, 3 - y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(1, 4 + y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(6, 3 - y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(6, 4 + y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(7, 3 - y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(7, 4 + y), apply_offset=apply_offset)
                    elif col_key == "col_4":
                        # Column 4 and 5
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(3, 3 - y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(3, 4 + y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(4, 3 - y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(4, 4 + y), apply_offset=apply_offset)

            # We show this row to the device
            # self.device.display(self.canvas.get_image())
            self.device.display(image)
            time.sleep(delay)
        
        # And now we move the bars down again to zero
        for y in range(3, -1, -1):

            # We go through each column to see if we need to turn off at this row
            for col_key, col_value in max_values.items():
                if col_value > y:

                    # We just skip the lowest one
                    # if col_key == "col_1":
                    #     # Column 1 and 7
                    #     canvas.point((0, 3 - y), self.OFF)
                    #     canvas.point((0, 4 + y), self.OFF)
                    #     canvas.point((7, 3 - y), self.OFF)
                    #     canvas.point((7, 4 + y), self.OFF)
                    # Removing the second lowest to give a separation space betweem 3 and 4
                    # if col_key == "col_2":
                    #     # Column 1 and 8
                    #     canvas.point((0, 3 - y), self.OFF)
                    #     canvas.point((0, 4 + y), self.OFF)
                    #     canvas.point((7, 3 - y), self.OFF)
                    #     canvas.point((7, 4 + y), self.OFF)
                    if col_key == "col_3":
                        # Column 2, 3 (left, -1 for a separation column), 6 and 7 (right, +1 for a separation column)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(4, 4 + y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(0, 3 - y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(0, 4 + y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(1, 3 - y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(1, 4 + y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(6, 3 - y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(6, 4 + y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(7, 3 - y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(7, 4 + y), apply_offset=apply_offset)
                    elif col_key == "col_4":
                        # Column 4 and 5
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(3, 3 - y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(3, 4 + y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(4, 3 - y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(4, 4 + y), apply_offset=apply_offset)

            # We show this row to the device
            self.device.display(image)
            # time.sleep(delay)

    def show_init_step(self, step):

        draw = self.canvas.get_canvas(reset_base_image = False)
        self._soft_clear_rectangle(draw=draw)
        rows = math.floor(step / 8) + 1
        rows = rows if rows > 1 else 1
        for y in range(0, rows):
            cols = 8 if y < rows - 1 else step % 8
            for x in range(0, cols):
                self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x,  y))
        self.device.display(self.canvas.get_image())
    
    def show_cross(self):
        draw = self.canvas.get_canvas(reset_base_image = False)
        self._soft_clear_rectangle(draw=draw)
        for i in range(0,8):
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(i, i))
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(i, i))
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(7 - i, i))
        self.device.display(self.canvas.get_image())
    
    def show_interaction_holding_percentage(self, percentage: int):
        '''
        Shows on the Matrix LED a percentage bar indicating how much time is left
        for the user to hold the interaction (i.e., speak).

        Args:
            percentage: The percentage of time left (0-100).
        '''
        draw = self.canvas.get_canvas(reset_base_image = False)
        self._soft_clear_rectangle(draw=draw)

        # Calculate how many columns to light up
        columns_to_light = math.ceil((percentage / 100) * 8)
        for x in range(0, columns_to_light):
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 7))
        self._xlog.debug(f"Displaying interaction percent {percentage}% ({columns_to_light} columns)")
        self.device.display(self.canvas.get_image())

    def draw_led_point_over_lcd_canvas(self, draw: ImageDraw.ImageDraw, point: Point, color: str = None, apply_offset: bool = True):
        '''
        Draws a point on the LCD canvas representing a round LED point,
        emulating a 8x8 Matrix LED.

        Args:
            point: The point to draw.
            color: The color to use.
        '''
        if color is None:
            color = self.canvas.COLOR_RED
        
        # Take in account the rounded shape of the LCD.
        # The corners have 40 pixels (square of 40p with one edge very rounded), so the area usable needs to be adjusted.
        # Let's just shrink the width only for simplicity.
        offset_x = self.LED_TO_LCD_OFFSET_X if apply_offset else 0

        # Each LED is represented by a 8x8 square on the LCD
        radius = 4  # Half of 8

        # We need to convert the point from a 8x8 Matrix LED to LCD coordinates, based on the full LCD size.
        # And also correct the radius to be relative to the LCD size.
        x = point.x * (self._display_size.x // 8) + offset_x // 2
        y = point.y * (self._display_size.y // 8)
        radius = min(self._display_size.x + offset_x // 16, self._display_size.y // 16)

        draw.circle(
            Point(x + radius, y + radius).to_image_point(),
            radius=radius,
            fill=color,
            outline=color)