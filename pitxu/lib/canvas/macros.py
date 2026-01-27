from PIL import ImageDraw,ImageFont, Image

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.objects import Rectangle, Line, Point
from pitxu.lib.canvas.canvas import Canvas
from pitxu.lib.abstract.device import Device
from pitxu.lib.interaction.CommConstants import BackgroundComm, ForegroundComm

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

    # BACKGROUND_DEFAULT: str = "default"
    # LED_EFFECT_LOOP_ITERATIONS: dict = {
    #     BackgroundComm.THINKING: 16,
    #     BackgroundComm.SPEAKING: 8,
    #     BackgroundComm.INITIAL_PHASE: 1,
    #     BackgroundComm.HOLDER_PERCENTAGE: 1,
    #     BACKGROUND_DEFAULT: 1
    # }

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

    def get_canvas(self) -> Canvas:
        return self.canvas

    def get_device(self) -> Device:
        return self.device

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
        draw = self.canvas.get_canvas(reset_base_image=False)

        # Draw the startup splash
        self.draw_startup_splash(draw=draw)
        
        # Flush the image (generated from the canvas) to the device
        self.device.display(self.canvas.get_image())
    
    def draw_startup_splash(self, draw: ImageDraw.ImageDraw):

        # Configurations
        padding = 15

        # Main title
        title = self._xconfig.get("app.name")
        version = self._xparams.get("app_version")
        draw.text(Point(self._display_size.x / 2, self._display_size.y / 4).to_image_point(),
                    text = title + "  v" + version, 
                    font = self.canvas.FONT_HUGE, 
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")
        
        # Draw a line between the title and the subtitle
        draw.line(
            Rectangle(
                Point(padding, (self._display_size.y / 2) - 10), 
                Point(self._display_size.x - padding, (self._display_size.y / 2) - 10)
            ).to_image_rectangle(),
            fill = self.canvas.COLOR_FOREGROUND,
            width = 1)
        
        # Subtitle
        subtitle = "Chatbot: " + ("mocked" if self._xconfig.get("chatbot.mock", True) else "real") + \
                    " | eInk: " + ("mocked" if self._xconfig.get("eink.mock", True) else "real") + \
                    "\nLED Matrix: " + ("mocked" if self._xconfig.get("matrix_led.mock", True) else "real") + \
                    " | LCD: " + ("mocked" if self._xconfig.get("lcd.mock", True) else "real") + \
                    "\nSTT: " + ("mocked" if self._xconfig.get("speech-to-text.mock", True) else "real") + \
                    " | TTS: " + ("mocked" if self._xconfig.get("text-to-speech.mock", True) else "real") + \
                    "\nUPS: " + ("mocked" if self._xconfig.get("ups.mocked", True) else "real") + \
                    " | GPIO: " + ("real" if self._xconfig.get("gpio.enabled", False) else "mocked")
                    
        draw.text(Point(self._display_size.x / 2, (self._display_size.y / 4) * 3).to_image_point(),
                    text = subtitle, 
                    font = self.canvas.FONT_TINY, 
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")

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
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")
        
        # Flush the image (generated from the canvas) to the device
        self.device.display(self.canvas.get_image())

    def arbitrary_text_centered(self, text: str):

        draw = self.canvas.get_canvas(reset_base_image=False)

        self.draw_arbitrary_text_centered(draw=draw, text=text)
        
        self.device.display(self.canvas.get_image())
    
    def draw_arbitrary_text_centered(self, draw: ImageDraw.ImageDraw, text: str):
        draw.text(Point(self._display_size.x / 2, self._display_size.y / 2).to_image_point(),
                    text = text,
                    font = self.canvas.FONT_HUGE,
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")

    def arbitrary_text_with_icon(
            self,
            text: str = None, 
            icon: str = None, 
            font_size: int = 24, 
            header: str = None, 
            font_header_size: int = 32,
            padding: int = 5) -> str:

        self.draw_arbitrary_text_with_icon(
            draw = self.canvas.get_canvas(reset_base_image=True),
            text = text,
            icon = icon,
            font_size = font_size,
            header = header,
            font_header_size = font_header_size,
            padding = padding)
        
        # Flush the image (generated from the canvas) to the device
        self.device.display(self.canvas.get_image())
    
    def draw_arbitrary_text_with_icon(
            self,
            draw: ImageDraw.ImageDraw,
            text: str = None, 
            icon: str = None, 
            font_size: int = 24, 
            header: str = None, 
            font_header_size: int = 32,
            padding: int = 5) -> str:

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
            draw.text(header_anchor.to_image_point(),
                text = f"{header_emoji}{header}",
                font = self.canvas.get_font_by_size(font_header_size),
                fill = self.canvas.COLOR_FOREGROUND,
                anchor = "mm",
                align = "center")

        if text:
            font = self.canvas.get_font_by_size(font_size)
            padding = 5
            value = self.wrap_text_if_needed(
                canvas=draw,
                text=f"{text_emoji}{text}",
                max_width=self._display_size.x - (2 * padding),
                font=font
            )
            draw.multiline_text(text_anchor.to_image_point(),
                text = value,
                font = font,
                fill = self.canvas.COLOR_FOREGROUND,
                anchor = "mm",
                align = "center")
    
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
            color = self.canvas.COLOR_BACKGROUND

        point_1 = Point(0, 0)
        point_2 = Point(self._display_size.x, self._display_size.y)
        draw.rectangle(
            Rectangle(point_1, point_2).to_image_rectangle(),
            outline=color,
            fill=color)
    
    # ------ Matrix Led effects adapted to LCD -------

    def kitt_horizontal_effect(self, delay: float = 0.1, should_stop: bool = False):
        self._log_debug("Starting KITT effect")

        draw = self.canvas.get_canvas(reset_base_image = False)
        self._soft_clear_rectangle(draw=draw)
        image = self.canvas.get_image()

        # Move right
        for i in range(8):
            self.draw_kitt_horizontal_effect_left(draw=draw, step=i)

            self.device.display(image)
            time.sleep(delay)

        # Move left
        for i in range(8):
            self.draw_kitt_horizontal_effect_right(draw=draw, step=i)

            self.device.display(image)
            time.sleep(delay)
    
    def draw_kitt_horizontal_effect_right(self, draw: ImageDraw.ImageDraw, step: int = None):
        counter = 0
        apply_offset = False

        for x in range(8):
            self._soft_clear_rectangle(draw=draw)
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 3), apply_offset=apply_offset)
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 4), apply_offset=apply_offset)
        
            # We count which is the current step for the drawing.
            # If we have reached the step, we stop drawing more.
            if step is not None and counter >= step:
                return
            else:
                counter += 1
    
    def draw_kitt_horizontal_effect_left(self, draw: ImageDraw.ImageDraw, step: int = None):
        counter = 0
        apply_offset = False

        for x in range(6,-1,-1):
            self._soft_clear_rectangle(draw=draw)
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 3), apply_offset=apply_offset)
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 4), apply_offset=apply_offset)
        
            # We count which is the current step for the drawing.
            # If we have reached the step, we stop drawing more.
            if step is not None and counter >= step:
                return
            else:
                counter += 1
    
    def kitt_speaking_effect_vu_meter(self, col_1: int, col_2: int, col_3: int, col_4: int, delay: float = 0.01):
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

        # Drawing the bars up. In this this method we draw all the steps at once
        for i in range(4):
            # self.draw_kitt_speaking_effect_vu_meter(draw=draw, max_values=max_values, step=i)
            self.draw_kitt_speaking_effect_vu_meter_increase(draw=draw, step=i)

            # We show this row to the device
            # self.device.display(self.canvas.get_image())
            self.device.display(image)
            time.sleep(delay)
        
        # And now we move the bars down again to zero
        for i in range(4):
            # self.clear_kitt_speaking_effect_vu_meter(draw=draw, max_values=max_values, step=i)
            self.draw_kitt_speaking_effect_vu_meter_decrease(draw=draw, step=i)

            # We show this row to the device
            self.device.display(image)
            time.sleep(delay)
    
    def _draw_kitt_mouth_frame(self, draw: ImageDraw.ImageDraw, frame: int):
        '''
        Draws the KITT mouth frame on the given canvas.

        It is meant to be used as a base for the speaking effect.
        '''
        apply_offset = False

        max_values = {
            "col_1": 0,
            "col_2": 0,
            "col_3": 2,
            "col_4": 4,
        }

        for y in range(0, frame):

            # We go through each column to see if we need to light it at this row
            for col_key, col_value in max_values.items():
                if col_key == "col_3":
                    if col_value > y:
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
                    if col_value > y:
                        # Column 4 and 5
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(3, 3 - y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(3, 4 + y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(4, 3 - y), apply_offset=apply_offset)
                        self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(4, 4 + y), apply_offset=apply_offset)

    def draw_kitt_speaking_effect_vu_meter_increase(self, draw: ImageDraw.ImageDraw, step: int = None):
        counter = 0

        # We go row by row from the middle point to the top and bottom extremes
        for frame in range(1, 5):

            # Every frame needs to be cleared first, to avoid having an effect of overlaying frames
            self._soft_clear_rectangle(draw=draw)

            # Every iteration here is a full frame to be drawn
            self._draw_kitt_mouth_frame(draw=draw, frame=frame)
                
            # We count which is the current step for the drawing.
            # If we have reached the step, we stop drawing more.
            # This way we can flush to the device in the steps we want.
            if step is not None and counter >= step:
                return
            else:
                counter += 1
    
    def draw_kitt_speaking_effect_vu_meter_decrease(self, draw: ImageDraw.ImageDraw, step: int = None):
        counter = 0

        # We go row by row from the middle point to the top and bottom extremes
        for frame in range(3, -1, -1):

            # Every frame needs to be cleared first, to avoid having an effect of overlaying frames
            self._soft_clear_rectangle(draw=draw)

            # Every iteration here is a full frame to be drawn
            self._draw_kitt_mouth_frame(draw=draw, frame=frame)
                
            # We count which is the current step for the drawing.
            # If we have reached the step, we stop drawing more.
            # This way we can flush to the device in the steps we want.
            if step is not None and counter >= step:
                return
            else:
                counter += 1

    def show_init_step(self, phase):

        draw = self.canvas.get_canvas(reset_base_image = False)

        self.draw_init_phase(draw=draw, phase=phase)

        self.device.display(self.canvas.get_image())
    
    def draw_init_phase(self, draw: ImageDraw.ImageDraw, phase: int):

        # Initial Background Paint clear
        self._soft_clear_rectangle(draw=draw)

        rows = math.floor(phase / 8) + 1
        rows = rows if rows > 1 else 1
        for y in range(0, rows):
            cols = 8 if y < rows - 1 else phase % 8
            for x in range(0, cols):
                self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x,  y))
    
    def show_cross(self):
        draw = self.canvas.get_canvas(reset_base_image = False)
        self._soft_clear_rectangle(draw=draw)
        
        self.draw_cross(draw=draw)

        self.device.display(self.canvas.get_image())
    
    def draw_cross(self, draw: ImageDraw.ImageDraw):
        for i in range(0,8):
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(i, i))
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(i, i))
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(7 - i, i))
    
    def show_interaction_holding_percentage(self, percentage: int):
        '''
        Shows on the Matrix LED a percentage bar indicating how much time is left
        for the user to hold the interaction (i.e., speak).

        Args:
            percentage: The percentage of time left (0-100).
        '''
        draw = self.canvas.get_canvas(reset_base_image = False)

        self.draw_interaction_holding_percentage(draw=draw, percentage=percentage)

        self.device.display(self.canvas.get_image())
    
    def draw_interaction_holding_percentage(self, draw: ImageDraw.ImageDraw, percentage: int):
        '''
        Draws on the given canvas a percentage bar indicating how much time is left
        for the user to hold the interaction (i.e., speak).

        Args:
            draw: The canvas to draw on.
            percentage: The percentage of time left (0-100).
        '''

        # Initial Background Paint clear
        self._soft_clear_rectangle(draw=draw)

        # Calculate how many columns to light up
        columns_to_light = math.ceil((percentage / 100) * 8)
        for x in range(0, columns_to_light):
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 7))

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
        x = point.x * ((self._display_size.x - offset_x) // 8) + (offset_x // 2 + 1)
        y = point.y * ((self._display_size.y - 1) // 8)
        radius = min((self._display_size.x - offset_x) // 16, (self._display_size.y - 1) // 16)
        # radius = (self._display_size.x - offset_x) // 16

        draw.circle(
            (x + radius, y + radius),
            radius=radius,
            fill=color,
            outline=color)
    
    # ------ Main method (and helpers) to show on LCD display -------

    # def show_on_lcd_display(self, 
    #                         background_interaction: str = None,
    #                         foreground_interaction: str = None,
    #                         parameter: any = None):
    #     '''
    #     This is the main method to draw all components on the display.
    #     '''

    #     draw = self.canvas.get_canvas(reset_base_image = False)
    #     self._soft_clear_rectangle(draw=draw)
    #     # The "draw" object is linked to the canvas, so we can get the image from there
    #     # It gets updated as we draw on it, so is more efficient than getting it each time
    #     image = self.canvas.get_image()

    #     # We need to draw from background to foreground.
    #     # At this point, LED effects are the most background, so we draw them first.

    #     # Some of the LED effects are loops, so we need to handle the drawing via a loop
    #     # And then flush to the display at each step.
    #     if background_interaction is not None:
    #         iterations = self.LED_EFFECT_LOOP_ITERATIONS.get(background_interaction, 1)\
    #                         if background_interaction in self.LED_EFFECT_LOOP_ITERATIONS\
    #                         else self.LED_EFFECT_LOOP_ITERATIONS.get(self.BACKGROUND_DEFAULT, 1)
    #         for i in range(iterations):

    #             if background_interaction == BackgroundComm.THINKING:
    #                 step = i % 8
    #                 if i < 8:
    #                     self.draw_kitt_horizontal_effect_right(draw=draw, step=step )
    #                 else:
    #                     self.draw_kitt_horizontal_effect_left(draw=draw, step=step)
    #             elif background_interaction == BackgroundComm.SPEAKING:
    #                 # For speaking, we simulate some VU meter values
    #                 self.draw_kitt_speaking_effect_vu_meter(draw=draw, max_values=parameter, step=i + 1)
    #             elif background_interaction == BackgroundComm.INITIAL_PHASE:
    #                 self.draw_init_step(draw=draw, step=parameter)
    #             elif background_interaction == BackgroundComm.HOLDER_PERCENTAGE:
    #                 self.draw_interaction_holding_percentage(draw=draw, percentage=parameter)
    #             elif background_interaction == BackgroundComm.ERROR:
    #                 self.draw_cross(draw=draw)
    #             else:
    #                 self._xlog.warning(f"Unknown interaction [{background_interaction}] for drawing on LCD display, discarding.")
        
    #     # There are no loops for foreground interactions yet, so we just draw them once.
    #     # Still, we may not receive any foreground interaction.
    #     if foreground_interaction is not None:
            
    #         # Whatever we print here, make it over a semi-transparent frame
    #         self.draw_foreground_frame(draw=draw)

    #         if foreground_interaction == ForegroundComm.ARBITRARY_TEXT:
    #             self.draw_arbitrary_text_centered(draw=draw, text=parameter)
    #         elif foreground_interaction == ForegroundComm.ARBITRARY_TEXT_ICON:
    #             self.draw_arbitrary_text_with_icon(draw=draw, 
    #                                                 text=parameter.get("text"),
    #                                                 icon=parameter.get("icon"),
    #                                                 font_size=parameter.get("font_size", 24),
    #                                                 header=parameter.get("header"),
    #                                                 font_header_size=parameter.get("font_header_size", 32),
    #                                                 padding=parameter.get("padding", 5))
    #         else:
    #             self._xlog.warning(f"Unknown interaction [{foreground_interaction}] for drawing on LCD display, discarding.")

    #     # Finally, we show the image on the device
    #     self.device.display(image)
    
    def draw_foreground_frame(self, draw: ImageDraw.ImageDraw, padding: int = 10, radius: int = 10, frame_color: str = None):
        '''
        Draws a foreground frame on the given canvas, except if the Color Mode is "1" (monochrome),
        in which case it draws a solid empty rectangle.

        https://stackoverflow.com/a/43620169/1973860
        '''

        if frame_color is None:
            frame_color = self.canvas.COLOR_ORANGE

        if self.canvas.COLOR_MODE == "RGBA":
            TINT_COLOR = frame_color
            TRANSPARENCY = .25  # Degree of transparency, 0-100%
            OPACITY = int(255 * TRANSPARENCY)
            color = (TINT_COLOR[0], TINT_COLOR[1], TINT_COLOR[2], OPACITY)

            # Create an overlay image for the transparency effect
            overlay = Image.new(
                'RGBA', 
                self._display_size.to_image_point(), 
                (TINT_COLOR[0], TINT_COLOR[1], TINT_COLOR[2], 0))
            # Create a context for drawing things on it.
            draw_overlay = ImageDraw.Draw(overlay)

            # Draw a rounded rectangle on the overlay
            point_1 = Point(padding, padding)
            point_2 = Point(self._display_size.x - padding, self._display_size.y - padding)
            draw_overlay.rounded_rectangle(
                Rectangle(point_1, point_2).to_image_rectangle(),
                radius=radius,
                outline=frame_color,
                fill=color,
                corners=(True, True, True, True))

            # Now composite the overlay onto the original image
            self.canvas.combine_into_image(overlay)
        else:
            color = self.canvas.COLOR_BACKGROUND

            point_1 = Point(padding, padding)
            point_2 = Point(self._display_size.x - padding - 1, self._display_size.y - padding - 1)
            draw.rectangle(
                Rectangle(point_1, point_2).to_image_rectangle(),
                outline=frame_color,
                fill=color)
