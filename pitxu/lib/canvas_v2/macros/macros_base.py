from PIL import ImageDraw,ImageFont

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.canvas_v2.animations import Animations
from pitxu.lib.canvas_v2.layout_info import LayoutInfo
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

    layout_info: dict[str, dict[str, Rectangle]] = None
    color_scheme_info: dict[str, dict[str, any]] = None

    # Pixels to offset in X axis (both sides) when drawing LED points over the LCD canvas
    LED_TO_LCD_OFFSET_X: int = 0
    APPLY_LED_TO_LCD_OFFSET_TO_ALL: bool = False

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

    def get_display_size(self) -> Point:
        return self._display_size

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

    def base_frame_for_display_area(self, draw: ImageDraw.ImageDraw, params: dict[str, any]):
        '''
        

        Note about coordinates: There is a draw object per display area, merged into the main image.
            That's why the coordinates are relative to the display area, not to the full screen.
        '''

        display_area = params.get("display_area", "full_screen")
        
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

    #     display_area = params.get("display_area", "full_screen")

    #     if display_area in self.layout_info["relative"]:
    #         rectangle = self.layout_info["relative"][display_area]
    #         outline = self.canvas.COLOR_BACKGROUND
    #         fill = self.canvas.COLOR_BACKGROUND

    #         draw.rectangle(
    #             rectangle.to_image_rectangle(),
    #             outline=outline,
    #             fill=fill)