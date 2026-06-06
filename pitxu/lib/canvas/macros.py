from PIL import ImageDraw,ImageFont, Image

from pyxavi import Config, Dictionary, dd
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

    layout_info: dict[str, Rectangle] = None
    color_scheme_info: dict[str, dict[str, any]] = None

    # Pixels to offset in X axis (both sides) when drawing LED points over the LCD canvas
    LED_TO_LCD_OFFSET_X: int = 0
    APPLY_LED_TO_LCD_OFFSET_TO_ALL: bool = False

    VERBOSE_DEBUG: bool = False

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
        
        # Which offset to apply when drawing LED points over the LCD canvas
        if params.key_exists("led_to_lcd_offset_x"):
            self._xlog.debug("Using LED to LCD offset X from params: " + str(params.get("led_to_lcd_offset_x")))
            self.LED_TO_LCD_OFFSET_X = params.get("led_to_lcd_offset_x")
        if params.key_exists("apply_led_to_lcd_offset_to_all", False):
            self._xlog.debug("Using apply_led_to_lcd_offset_to_all from params: " + str(params.get("apply_led_to_lcd_offset_to_all")))
            self.APPLY_LED_TO_LCD_OFFSET_TO_ALL = params.get("apply_led_to_lcd_offset_to_all")
        
        self.log_summary("Macros Initialization", [
            ("Display Size", f"{self._display_size.x}x{self._display_size.y}"),
            ("LED_TO_LCD_OFFSET_X", f"{self.LED_TO_LCD_OFFSET_X} pixels"),
            ("APPLY_LED_TO_LCD_OFFSET_TO_ALL", self.APPLY_LED_TO_LCD_OFFSET_TO_ALL)
        ])
    
        # Calculate the layout info. Make sure that the padding is consistent (it may need a refactor)
        self.layout_info = self.get_layout_info(padding=10, corners_radius=10)
        # Get the color scheme info
        self.color_scheme_info = self.get_color_scheme_info()

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
            lines = text.split("\n")
            longest_line = max(lines, key=lambda line: canvas.textlength(line, font=font))
            width_text = canvas.textlength(longest_line, font)
            if(width_text <= max_width):
                return text
            else:
                new_text = ""
                for line in lines:
                    if canvas.textlength(line, font) > max_width:
                        words = line.split()
                        current_line = ""
                        
                        for word in words:
                            test_line = current_line + (" " if current_line != "" else "") + word
                            width_test_line = canvas.textlength(test_line, font)
                            if(width_test_line <= max_width):
                                current_line = test_line
                            else:
                                new_text += current_line + "\n"
                                current_line = word
                        new_text += current_line + "\n"
                    else:
                        new_text += line + "\n"
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

        offset_x = self.layout_info["top_right"].point_1.x
        offset_y = self.layout_info["top_right"].point_1.y
        max_x = self.layout_info["top_right"].point_2.x
        max_y = self.layout_info["top_right"].point_2.y
        width = max_x - offset_x
        height = max_y - offset_y

        # Configurations
        padding = 15

        # Main title
        title = self._xconfig.get("app.name")
        version = self._xparams.get("app_version")
        draw.text(Point(offset_x + width / 2, offset_y + height / 4).to_image_point(),
                    text = title + "  v" + version, 
                    font = self.canvas.FONT_HUGE, 
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")
        
        # Draw a line between the title and the subtitle
        draw.line(
            Rectangle(
                Point(offset_x + padding, offset_y + height / 2 - 10), 
                Point(offset_x + width - padding, offset_y + height / 2 - 10)
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
                    "\nUPS: " + ("mocked" if self._xconfig.get("ups.mock", True) else "real") + \
                    " | GPIO: " + ("mocked" if self._xconfig.get("gpio.mock", True) else "real")
                    
        draw.text(Point(offset_x + width / 2, offset_y + (height / 4) * 3).to_image_point(),
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
        offset_x = self.layout_info["top_right"].point_1.x
        offset_y = self.layout_info["top_right"].point_1.y
        max_x = self.layout_info["top_right"].point_2.x
        max_y = self.layout_info["top_right"].point_2.y
        width = max_x - offset_x
        height = max_y - offset_y
    
        draw.text(Point(offset_x + width / 2, offset_y + height / 2).to_image_point(),
                    text = text,
                    font = self.canvas.FONT_HUGE,
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")
    
    def code_block(self, text: str):

        draw = self.canvas.get_canvas(reset_base_image=False)

        self.draw_code_block(draw=draw, text=text)
        
        self.device.display(self.canvas.get_image())
    
    def draw_code_block(self, draw: ImageDraw.ImageDraw, text: str):
        """
        Draws a full screen code block, with the biggest font that fits in width, and centered in the remaining space if it does not fill all the height.
        Does not follow the layout, ot's an overlay over the whole screen, with a padding from the borders.
        """

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
            fill = self.canvas.COLOR_BLACK,
            anchor = "la",
            align= "left")
    
    def text_block(self, text: str):

        draw = self.canvas.get_canvas(reset_base_image=False)

        self.draw_text_block(draw=draw, text=text)
        
        self.device.display(self.canvas.get_image())
    
    def draw_text_block(self, draw: ImageDraw.ImageDraw, text: str):
        """
        Draws a full screen text block, with the biggest font that fits in width, and centered in the remaining space if it does not fill all the height.
        Does not follow the layout, ot's an overlay over the whole screen, with a padding from the borders.
        """

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
            fill = self.canvas.COLOR_BLACK,
            anchor = "la",
            align= "left")

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
        
        offset_x = self.layout_info["top_right"].point_1.x
        offset_y = self.layout_info["top_right"].point_1.y
        max_x = self.layout_info["top_right"].point_2.x
        max_y = self.layout_info["top_right"].point_2.y
        width = max_x - offset_x
        height = max_y - offset_y

        # calculate anchor points and emojis for header and text
        if header and text:
            header_anchor = Point(offset_x + width / 2, offset_y + height / 3)
            text_anchor = Point(offset_x + width / 2, offset_y + (height / 4) * 3)
            header_emoji = icon + " " if icon else ""
            text_emoji = ""
        elif header and not text:
            header_anchor = Point(offset_x + width / 2, offset_y + height / 2)
            header_emoji = icon + " " if icon else ""
        elif not header and text:
            text_anchor = Point(offset_x + width / 2, offset_y + height / 2)
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
                max_width=width - (2 * padding),
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
    
    def soft_clear(self, display_area: str = "full_screen"):

        # First create a canvas
        draw = self.canvas.get_canvas()

        # Create a background color rectangle with the sizes of the screen
        self._soft_clear_rectangle(draw=draw, display_area=display_area)

        # Flush the image (generated from the canvas) to the device
        self.device.display(self.canvas.get_image())

    def _soft_clear_rectangle(self, draw: ImageDraw.ImageDraw, display_area: str = "full_screen", color: str = None):
        '''
        Draws a rectangle over the given canvas.
        '''
        if color is None:
            color = self.canvas.COLOR_BACKGROUND
        
        # Set the default, which is non-RGBA.
        outline = color
        fill = color
        rectangle: Rectangle = None
        
        found_area = False
        if display_area == "full_screen":
            offset_x = 0
            offset_y = 0
            max_x = self._display_size.x
            max_y = self._display_size.y
            rectangle = Rectangle(Point(offset_x, offset_y), Point(max_x, max_y))
            found_area = True
        else:
            if display_area in self.layout_info:
                rectangle = self.layout_info[display_area]
                outline = self.color_scheme_info[display_area]["outline"]
                fill = self.color_scheme_info[display_area]["fill"]
                found_area = True
            
        if not found_area:
            self._xlog.warning(f"Unrecognized display area [{display_area}] for soft clear.")
            return
        else:
            if self.canvas.COLOR_MODE == "RGBA":
                draw.rounded_rectangle(
                    rectangle.to_image_rectangle(),
                    radius=self.layout_info["corners_radius"],
                    outline=outline,
                    fill=fill,
                    corners=(True, True, True, True))
            else:
                draw.rectangle(
                    rectangle.to_image_rectangle(),
                    outline=outline,
                    fill=fill)
    
    # ------ Background effects adapted to LCD -------

    def kitt_horizontal_effect(self, delay: float = 0.1, color: str = None):
        self._log_debug("Starting KITT effect")

        draw = self.canvas.get_canvas(reset_base_image = False)
        self._soft_clear_rectangle(draw=draw, display_area="top_left")
        image = self.canvas.get_image()

        # Move right
        for i in range(8):
            self.draw_kitt_horizontal_effect_left(draw=draw, frame=i, color=color)

            self.device.display(image)
            time.sleep(delay)

        # Move left
        for i in range(8):
            self.draw_kitt_horizontal_effect_right(draw=draw, frame=i, color=color)

            self.device.display(image)
            time.sleep(delay)
    
    def draw_kitt_horizontal_effect_right(self, draw: ImageDraw.ImageDraw, frame: int = None, color: str = None):
        counter = 0
        apply_offset = self.APPLY_LED_TO_LCD_OFFSET_TO_ALL

        for x in range(8):
            self._soft_clear_rectangle(draw=draw, display_area="top_left")
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 3), apply_offset=apply_offset, color=color)
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 4), apply_offset=apply_offset, color=color)
        
            # We count which is the current frame for the drawing.
            # If we have reached the frame, we stop drawing more.
            if frame is not None and counter >= frame:
                return
            else:
                counter += 1
    
    def draw_kitt_horizontal_effect_left(self, draw: ImageDraw.ImageDraw, frame: int = None, color: str = None):
        counter = 0
        apply_offset = self.APPLY_LED_TO_LCD_OFFSET_TO_ALL

        for x in range(6,-1,-1):
            self._soft_clear_rectangle(draw=draw, display_area="top_left")
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 3), apply_offset=apply_offset, color=color)
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 4), apply_offset=apply_offset, color=color)
        
            # We count which is the current frame for the drawing.
            # If we have reached the frame, we stop drawing more.
            if frame is not None and counter >= frame:
                return
            else:
                counter += 1
    
    def kitt_speaking_effect(self, col_1: int, col_2: int, col_3: int, col_4: int, delay: float = 0.01):
        '''
        KITT speaking effect using VU Meter columns

        Be careful, it relies on having a HandableCanvas instance opened previously, and
        needs to be closed afterwards.
        '''
        draw = self.canvas.get_canvas(reset_base_image = False)
        self._soft_clear_rectangle(draw=draw, display_area="top_left")
        # The "draw" object is linked to the canvas, so we can get the image from there
        # It gets updated as we draw on it, so is more efficient than getting it each time
        image = self.canvas.get_image()

        # Drawing the bars up. In this this method we draw all the steps at once
        for i in range(4):
            # self.draw_kitt_speaking_effect(draw=draw, max_values=max_values, step=i)
            self.draw_kitt_speaking_effect_increase(draw=draw, frame=i)

            # We show this row to the device
            # self.device.display(self.canvas.get_image())
            self.device.display(image)
            time.sleep(delay)
        
        # And now we move the bars down again to zero
        for i in range(4):
            # self.clear_kitt_speaking_effect(draw=draw, max_values=max_values, step=i)
            self.draw_kitt_speaking_effect_decrease(draw=draw, frame=i)

            # We show this row to the device
            self.device.display(image)
            time.sleep(delay)
    
    def _draw_kitt_mouth_frame(self, draw: ImageDraw.ImageDraw, frame: int):
        '''
        Draws the KITT mouth frame on the given canvas.

        It is meant to be used as a base for the speaking effect.
        '''
        # It was set as False, but we want to also follow the class instance setting, that gets it defined from params
        apply_offset = self.APPLY_LED_TO_LCD_OFFSET_TO_ALL

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

    def draw_kitt_speaking_effect_increase(self, draw: ImageDraw.ImageDraw, frame: int = None):
        counter = 0

        # We go row by row from the middle point to the top and bottom extremes
        for drawing_frame in range(1, 5):

            # Every frame needs to be cleared first, to avoid having an effect of overlaying frames
            self._soft_clear_rectangle(draw=draw, display_area="top_left")

            # Every iteration here is a full frame to be drawn
            self._draw_kitt_mouth_frame(draw=draw, frame=drawing_frame)
                
            # We count which is the current step for the drawing.
            # If we have reached the frame, we stop drawing more.
            # This way we can flush to the device in the frames we want.
            if frame is not None and counter >= frame:
                return
            else:
                counter += 1
    
    def draw_kitt_speaking_effect_decrease(self, draw: ImageDraw.ImageDraw, frame: int = None):
        counter = 0

        # We go row by row from the middle point to the top and bottom extremes
        for drawing_frame in range(3, -1, -1):

            # Every frame needs to be cleared first, to avoid having an effect of overlaying frames
            self._soft_clear_rectangle(draw=draw, display_area="top_left")

            # Every iteration here is a full frame to be drawn
            self._draw_kitt_mouth_frame(draw=draw, frame=drawing_frame)
                
            # We count which is the current step for the drawing.
            # If we have reached the frame, we stop drawing more.
            # This way we can flush to the device in the frames we want.
            if frame is not None and counter >= frame:
                return
            else:
                counter += 1

    def show_init_phase(self, phase):

        draw = self.canvas.get_canvas(reset_base_image = False)

        self.draw_init_phase(draw=draw, phase=phase)

        self.device.display(self.canvas.get_image())
    
    def draw_init_phase(self, draw: ImageDraw.ImageDraw, parameter: dict):

        # Initial Background Paint clear
        self._soft_clear_rectangle(draw=draw, display_area="top_left")

        phase = parameter.get("phase", 0)
        text = parameter.get("text", None)

        rows = math.floor(phase / 8) + 1
        rows = rows if rows > 1 else 1
        for y in range(0, rows):
            cols = 8 if y < rows - 1 else phase % 8
            for x in range(0, cols):
                self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x,  y))
    
    def draw_combined_init_phase(self, draw: ImageDraw.ImageDraw, parameter: dict):
        '''
        Draws the combined status (bottom-center) and foreground (top-right) for the init phase. 
        It is meant to be used on the new Pitxu main, as it has more space to show both the progress and the details.
        The old Pitxu client should still use the draw_foreground_init_phase() due to the small screen.
        '''
        fore_offset_x = self.layout_info["top_right"].point_1.x
        fore_offset_y = self.layout_info["top_right"].point_1.y
        fore_max_x = self.layout_info["top_right"].point_2.x
        fore_max_y = self.layout_info["top_right"].point_2.y
        fore_width = fore_max_x - fore_offset_x
        fore_height = fore_max_y - fore_offset_y

        status_offset_x = self.layout_info["bottom_center"].point_1.x
        status_offset_y = self.layout_info["bottom_center"].point_1.y
        status_max_x = self.layout_info["bottom_center"].point_2.x
        status_max_y = self.layout_info["bottom_center"].point_2.y
        status_width = status_max_x - status_offset_x
        status_height = status_max_y - status_offset_y

        # Main title
        title = self._xconfig.get("app.name")
        version = self._xparams.get("app_version")
        draw.text(Point(fore_offset_x + fore_width / 2, fore_offset_y + fore_height / 3 * 1.5).to_image_point(),
                    text = title + "  v" + version, 
                    font = self.canvas.FONT_HUGE, 
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")
        
        # Mocked features line
        mocked_line = "Chatbot, STT, TTS,\nFore, Back, UPS, GPIO"
        draw.text(Point(status_offset_x + status_width / 2, status_offset_y + status_height / 8 * 3).to_image_point(),
                    text = mocked_line, 
                    font = self.canvas.FONT_SMALL, 
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")
        
        # Phases
        phase = parameter.get("phase", 0)
        text = parameter.get("text", None)
        draw.text(Point(status_offset_x + status_width / 2, status_offset_y + status_height / 8 * 6).to_image_point(),
                    # text = f"{phase} - {text}", 
                    text = text,
                    font = self.canvas.FONT_SMALL, 
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")

    def draw_foreground_init_phase(self, draw: ImageDraw.ImageDraw, parameter: dict):
        '''
        Draws the foreground if the init phase. 
        This replaces the Background one used on Pitxu main. 
        Pitxu client should still use it due to the small screen.
        New Pitxu main should use a new status area (bottom-center) for the detailed, and the app name and version in the top-right

        2026-06-05: Offset and coords adapted to follow the self.layout_info. Assuming full screen.
        '''
        offset_x = self.layout_info["padding"]
        offset_y = self.layout_info["padding"]
        max_x = self._display_size.x - self.layout_info["padding"]
        max_y = self._display_size.y - self.layout_info["padding"]
        width = max_x - offset_x
        height = max_y - offset_y

        # Configurations
        padding_line = 15

        # Main title
        title = self._xconfig.get("app.name")
        version = self._xparams.get("app_version")
        draw.text(Point(offset_x + width / 2, offset_y + height / 8 * 1.5).to_image_point(),
                    text = title + "  v" + version, 
                    font = self.canvas.FONT_HUGE, 
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")
        
        # Mocked features line
        mocked_line = "Chatbot, STT, TTS,\nFore, Back, UPS, GPIO"
        draw.text(Point(offset_x + width / 2, offset_y + height / 8 * 4).to_image_point(),
                    text = mocked_line, 
                    font = self.canvas.FONT_SMALL, 
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")
        
        # Draw a line between the title and the subtitle
        draw.line(
            Rectangle(
                Point(offset_x + padding_line, offset_y + height / 3 * 2), 
                Point(offset_x + width - padding_line, offset_y + height / 3 * 2)
            ).to_image_rectangle(),
            fill = self.canvas.COLOR_FOREGROUND,
            width = 1)
        
        # Phases
        phase = parameter.get("phase", 0)
        text = parameter.get("text", None)
        draw.text(Point(offset_x + width / 2, offset_y + height / 8 * 6.5).to_image_point(),
                    # text = f"{phase} - {text}", 
                    text = text,
                    font = self.canvas.FONT_SMALL, 
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")
    
    def draw_arbitrary_icon(self, draw: ImageDraw.ImageDraw, icon: str, text: str = None, color: str = None):
        '''
        Draws an arbitrary icon and text in the given color over the frame as is.

        2026-06-05: Offset and coords adapted to follow the self.layout_info. Assuming top-right area.
        '''
        offset_x = self.layout_info["top_right"].point_1.x
        offset_y = self.layout_info["top_right"].point_1.y
        max_x = self.layout_info["top_right"].point_2.x
        max_y = self.layout_info["top_right"].point_2.y
        width = max_x - offset_x
        height = max_y - offset_y

        if color is None:
            color = self.canvas.COLOR_FOREGROUND

        draw.text(Point(offset_x + width / 2, offset_y + height / 2 - (30 if text else 0)).to_image_point(),
                    text = icon,
                    font = self.canvas.FONT_ULTRA, 
                    fill = color,
                    anchor = "mm",
                    align = "center")
        if text:
            draw.text(Point(offset_x + width / 2, offset_y + height / 2 + 30).to_image_point(),
                    text = f"{icon}\n{text}" if text else icon, 
                    font = self.canvas.FONT_BIG, 
                    fill = color,
                    anchor = "mm",
                    align = "center")
    
    def show_cross(self):
        draw = self.canvas.get_canvas(reset_base_image = False)
        self._soft_clear_rectangle(draw=draw, display_area="top_left")
        
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
        self._soft_clear_rectangle(draw=draw, display_area="top_left")

        # Calculate how many columns to light up
        columns_to_light = math.ceil((percentage / 100) * 8)
        for x in range(0, columns_to_light):
            self.draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 7), apply_offset=False)

    def draw_led_point_over_lcd_canvas(self, draw: ImageDraw.ImageDraw, point: Point, color: str = None, apply_offset: bool = True):
        '''
        Draws a point on the LCD canvas representing a round LED point,
        emulating a 8x8 Matrix LED.

        2026-06-05: Offset and coords adapted to follow the self.layout_info. Assuming top-left area.

        Args:
            point: The point to draw.
            color: The color to use.
        '''
        if color is None:
            color = self.canvas.COLOR_RED
        
        # Take in account the rounded shape of the LCD (this is only useful for physical rounded screens like PiSugar Whisplay).
        # The corners have 40 pixels (square of 40p with one edge very rounded), so the area usable needs to be adjusted.
        # Let's just shrink the width only for simplicity.
        offset_x = self.LED_TO_LCD_OFFSET_X if apply_offset else 0

        # Now also take in account the layout info
        padding = 2
        temp_max_x = self.layout_info["top_left"].point_2.x
        temp_max_y = self.layout_info["top_left"].point_2.y
        max_x = min(temp_max_x, temp_max_y) + padding
        max_y = min(temp_max_x, temp_max_y)
        extra_offset_x = 0
        extra_offset_y = 0
        if max_x == temp_max_x + padding:
            # We are limited by the width, the applied extra offset is over the height.
            extra_offset_y = temp_max_y - max_y
        elif max_y == temp_max_y:
            # We are limited by the height, the applied extra offset is over the width.
            extra_offset_x = temp_max_x - max_x
            
        offset_x += self.layout_info["top_left"].point_1.x + (padding * 2) + extra_offset_x + 1
        offset_y = self.layout_info["top_left"].point_1.y + (padding * 2) + extra_offset_y + 1
        width = max_x - offset_x
        height = max_y - offset_y

        # Each LED is represented by a 8x8 square on the LCD
        radius = 4  # Half of 8

        # We need to convert the point from a 8x8 Matrix LED to LCD coordinates, based on the full LCD size.
        # And also correct the radius to be relative to the LCD size.
        x = point.x * ((width) // 8) + (offset_x)
        y = point.y * ((height) // 8) + (offset_y)
        radius = max((width) // 16, (height) // 16) - 2

        draw.circle(
            (x + radius, y + radius),
            radius=radius,
            fill=color,
            outline=color)
    
    def get_layout_info(self, padding: int = 10, corners_radius: int = 10) -> dict[str, Rectangle]:
        '''
        Returns the layout information of the LCD display, based on the padding and the division in 2 rows.

        It is meant to be used as a helper for drawing the foreground frame, but can be used for other purposes.
        '''
        useful_width = self._display_size.x - (2 * padding)
        useful_height = self._display_size.y - (2 * padding)

        rows_percentages = [0.6, 0.4]
        top_columns_percentages = [0.3, 0.7]
        bottom_columns_percentages = [0.10, 0.8, 0.10]

        top_left = Rectangle(
            Point(padding, padding),
            Point(math.ceil(useful_width * top_columns_percentages[0]), (padding // 2) + math.ceil(useful_height * rows_percentages[0]))
        )
        top_right = Rectangle(
            Point(padding + math.ceil(useful_width * top_columns_percentages[0]), padding),
            Point(padding + useful_width, (padding // 2) + math.ceil(useful_height * rows_percentages[0]))
        )
        bottom_left = Rectangle(
            Point(padding, padding + (padding // 2) + math.ceil(useful_height * rows_percentages[0])),
            Point(padding + math.ceil(useful_width * bottom_columns_percentages[0]), padding + useful_height)
        )
        bottom_center = Rectangle(
            Point((padding * 2) + math.ceil(useful_width * bottom_columns_percentages[0]), padding + (padding // 2) + math.ceil(useful_height * rows_percentages[0])),
            Point((padding * 2) + math.ceil((useful_width - padding) * (bottom_columns_percentages[0] + bottom_columns_percentages[1])), padding + useful_height)
        )
        bottom_right = Rectangle(
            Point((padding * 2) + math.ceil((useful_width * bottom_columns_percentages[0]) + (useful_width * bottom_columns_percentages[1])), padding + (padding // 2) + math.ceil(useful_height * rows_percentages[0])),
            Point(padding + useful_width, padding + useful_height)
        )

        return {
            "top_left": top_left,
            "top_right": top_right,
            "bottom_left": bottom_left,
            "bottom_center": bottom_center,
            "bottom_right": bottom_right,
            "padding": padding,
            "corners_radius": corners_radius,
        }
    
    def get_color_scheme_info(self, frame_color: str = None, opacity: float = 0.25) -> dict[str, dict[str, any]]:
        """
        Returns the color scheme information for the different areas of the LCD display, based on the color mode.
        """

        # -- Let's start by a simple default, no RGBA --
        # This will be the outline color.
        if frame_color is None:
            frame_color = self.canvas.COLOR_ORANGE
        # Now the fill color.
        color = self.canvas.COLOR_BACKGROUND
        # This is not needed by the non-RGBA modes, but we define it here to avoid having it undefined in the RGBA mode.
        overlay: Image.Image = None

        # -- Now, if we have RGBA --
        if self.canvas.COLOR_MODE == "RGBA":
            TINT_COLOR = frame_color
            # Sorry, fellow reader, I understand "less transparency, more opaque", so 0.25 opacity is closer to no-transparent.
            TRANSPARENCY = opacity  # Degree of transparency, 0-100%
            OPACITY = int(255 * TRANSPARENCY)
            color = (TINT_COLOR[0], TINT_COLOR[1], TINT_COLOR[2], OPACITY)

            # Create an overlay image for the transparency effect.
            # ATTENTION: This is meant to be a template, copy it when using it!
            #   overlay.copy() to use it, as we will need to draw on it and we don't want to modify the original one.
            overlay = Image.new(
                'RGBA', 
                self._display_size.to_image_point(), 
                (TINT_COLOR[0], TINT_COLOR[1], TINT_COLOR[2], 0))

        return {
            "top_left": {
                "outline": frame_color,
                # We don't want any background in the top-left corner
                "fill": None
            },
            "top_right": {
                "outline": frame_color,
                "fill": color
            },
            "bottom_left": {
                "outline": frame_color,
                "fill": color
            },
            "bottom_center": {
                "outline": frame_color,
                "fill": color
            },
            "bottom_right": {
                "outline": frame_color,
                "fill": color
            },
            "overlay_image": overlay,
        }
    
    # ------ Main method (and helpers) to show on LCD display -------

    def draw_overall_full_frame(self, draw: ImageDraw.ImageDraw, padding: int = 10, radius: int = 10, frame_color: str = None, opacity: float = 0.25):
        '''
        Draws a full screen frame on the given canvas, with the given padding and radius.

        It is meant to be used as an overlay for the whole screen, to show any specific interaction.
        '''
        if frame_color is None:
            frame_color = self.canvas.COLOR_ORANGE

        if self.canvas.COLOR_MODE == "RGBA":
            TINT_COLOR = frame_color
            # Sorry, fellow reader, I understand "less transparency, more opaque", so 0.25 opacity is closer to no-transparent.
            TRANSPARENCY = opacity  # Degree of transparency, 0-100%
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
    
    def draw_foreground_frame(self, draw: ImageDraw.ImageDraw, padding: int = 10, radius: int = 10, frame_color: str = None, opacity: float = 0.25):
        '''
        Draws a foreground frame on the given canvas, except if the Color Mode is "1" (monochrome),
        in which case it draws a solid empty rectangle.

        https://stackoverflow.com/a/43620169/1973860
        '''

        # The screen is divided in 2 rows:
        #   - top: contains current interaction: mouth and text (question and answer)
        #   - bottom: contains additional information or status: buttons/icons and current action being executed.
        #
        # Top-left:
        #   - Interaction animation (mouth, emojis, etc.)
        # Top-right:
        #   - Current question and answer text (as has been fukll screen centered until now)
        # Bottom-left:
        #   - Status icons (Wifi, battery, etc.)
        # Bottom-center:
        #   - Current action being executed ("STT", "Chatbot", "External Tool (which)", etc.)
        # Bottom-right:
        #   - Action icons, color by action (STT grey: inactive, orange: transcribing but useless, green: transcribing to be used; Chatbot grey: inactive, blue: sent, orange: external tool, green: answering; Memory:...)
        #
        # Now defining the frame points
        # TODO: All of this should be re-thought. This should be a template, stored externally


        if self.canvas.COLOR_MODE == "RGBA":

            overlay: Image.Image = self.color_scheme_info["overlay_image"]
            overlay = overlay.copy()  # We copy it to avoid modifying the original one, which is stored in the color scheme info for re-use in other frames.
            draw_overlay = ImageDraw.Draw(overlay)

            # Draw all the rectangles given (they are already calculated to be inside the screen and with the padding)
            for name, rectangle in self.layout_info.items():
                if isinstance(rectangle, Rectangle):
                    draw_overlay.rounded_rectangle(
                        rectangle.to_image_rectangle(),
                        radius=radius,
                        outline=self.color_scheme_info[name]["outline"],
                        fill=self.color_scheme_info[name]["fill"],
                        corners=(True, True, True, True))

            # Now composite the overlay onto the original image
            self.canvas.combine_into_image(overlay)
        else:
            if frame_color is None:
                frame_color = self.canvas.COLOR_ORANGE
            color = self.canvas.COLOR_BACKGROUND

            point_1 = Point(padding, padding)
            point_2 = Point(self._display_size.x - padding - 1, self._display_size.y - padding - 1)
            draw.rectangle(
                Rectangle(point_1, point_2).to_image_rectangle(),
                outline=frame_color,
                fill=color)
