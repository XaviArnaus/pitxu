from PIL import ImageDraw

from pyxavi import Config, Dictionary, dd
from pitxu.lib.objects import Point

from pitxu.lib.canvas_v2.macros_base import MacrosBase

import math
import time

class MacrosBackground(MacrosBase):
    """
    Drawings that take place in the background, which is the "top-left" area of the layout.
    """

    # Pixels to offset in X axis (both sides) when drawing LED points over the LCD canvas
    LED_TO_LCD_OFFSET_X: int = 0
    APPLY_LED_TO_LCD_OFFSET_TO_ALL: bool = False

    def __init__(self, config: Config, params: Dictionary):
        super(MacrosBackground, self).__init__(config, params)

        # Which offset to apply when drawing LED points over the LCD canvas
        if params.key_exists("led_to_lcd_offset_x"):
            self._xlog.debug("Using LED to LCD offset X from params: " + str(params.get("led_to_lcd_offset_x")))
            self.LED_TO_LCD_OFFSET_X = params.get("led_to_lcd_offset_x")
        if params.key_exists("apply_led_to_lcd_offset_to_all", False):
            self._xlog.debug("Using apply_led_to_lcd_offset_to_all from params: " + str(params.get("apply_led_to_lcd_offset_to_all")))
            self.APPLY_LED_TO_LCD_OFFSET_TO_ALL = params.get("apply_led_to_lcd_offset_to_all")
        
        self.log_summary("Macros Background Initialization", [
            ("LED_TO_LCD_OFFSET_X", f"{self.LED_TO_LCD_OFFSET_X} pixels"),
            ("APPLY_LED_TO_LCD_OFFSET_TO_ALL", self.APPLY_LED_TO_LCD_OFFSET_TO_ALL)
        ])

        self._xlog.debug("Initialized MacrosBackground.")
    
    # def kitt_horizontal_effect(self, delay: float = 0.1, color: str = None):
    #     self._log_debug("Starting KITT effect")

    #     draw = self.canvas.get_canvas(reset_base_image = False)
    #     self.soft_clear_rectangle(draw=draw, display_area="top_left")
    #     image = self.canvas.get_image()

    #     # Move right
    #     for i in range(8):
    #         self.draw_kitt_horizontal_effect_left(draw=draw, frame=i, color=color)

    #         self.device.display(image)
    #         time.sleep(delay)

    #     # Move left
    #     for i in range(8):
    #         self.draw_kitt_horizontal_effect_right(draw=draw, frame=i, color=color)

    #         self.device.display(image)
    #         time.sleep(delay)
    
    def draw_kitt_horizontal_effect(self, draw: ImageDraw.ImageDraw, params: dict):
        """
        Draws the KITT horizontal effect on the LCD display, based on the given loop iterations counter and max value.
        It is meant to be called directly from the painting loop, so it can control which frame to draw based on the loop iteration counter.
        """
        current_loop_iteration = params.get("current_loop_iteration", 0)
        max_loop_iterations = params.get("max_loop_iterations", 0)
        color = params.get("color", None)

        frame = current_loop_iteration % (max_loop_iterations // 2)
        if current_loop_iteration < (max_loop_iterations // 2):
            self._log_debug(f"Painter Loop: Drawing Thinking Right screen on LCD display, frame [{frame}].")
            self._draw_kitt_horizontal_effect_right(draw=draw, frame=frame, color=color)
        else:
            self._log_debug(f"Painter Loop: Drawing Thinking Left screen on LCD display, frame [{frame}].")
            self._draw_kitt_horizontal_effect_left(draw=draw, frame=frame, color=color)
    
    def _draw_kitt_horizontal_effect_right(self, draw: ImageDraw.ImageDraw, frame: int = None, color: str = None):
        counter = 0
        apply_offset = self.APPLY_LED_TO_LCD_OFFSET_TO_ALL

        for x in range(8):
            self.base_frame_for_display_area(draw=draw, params={"display_area": "top_left"})
            self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 3), apply_offset=apply_offset, color=color)
            self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 4), apply_offset=apply_offset, color=color)
        
            # We count which is the current frame for the drawing.
            # If we have reached the frame, we stop drawing more.
            if frame is not None and counter >= frame:
                return
            else:
                counter += 1
    
    def _draw_kitt_horizontal_effect_left(self, draw: ImageDraw.ImageDraw, frame: int = None, color: str = None):
        counter = 0
        apply_offset = self.APPLY_LED_TO_LCD_OFFSET_TO_ALL

        for x in range(6,-1,-1):
            self.base_frame_for_display_area(draw=draw, params={"display_area": "top_left"})
            self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 3), apply_offset=apply_offset, color=color)
            self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 4), apply_offset=apply_offset, color=color)
        
            # We count which is the current frame for the drawing.
            # If we have reached the frame, we stop drawing more.
            if frame is not None and counter >= frame:
                return
            else:
                counter += 1
    
    # def kitt_speaking_effect(self, col_1: int, col_2: int, col_3: int, col_4: int, delay: float = 0.01):
    #     '''
    #     KITT speaking effect using VU Meter columns

    #     Be careful, it relies on having a HandableCanvas instance opened previously, and
    #     needs to be closed afterwards.
    #     '''
    #     draw = self.canvas.get_canvas(reset_base_image = False)
    #     self.soft_clear_rectangle(draw=draw, display_area="top_left")
    #     # The "draw" object is linked to the canvas, so we can get the image from there
    #     # It gets updated as we draw on it, so is more efficient than getting it each time
    #     image = self.canvas.get_image()

    #     # Drawing the bars up. In this this method we draw all the steps at once
    #     for i in range(4):
    #         # self.draw_kitt_speaking_effect(draw=draw, max_values=max_values, step=i)
    #         self.draw_kitt_speaking_effect_increase(draw=draw, frame=i)

    #         # We show this row to the device
    #         # self.device.display(self.canvas.get_image())
    #         self.device.display(image)
    #         time.sleep(delay)
        
    #     # And now we move the bars down again to zero
    #     for i in range(4):
    #         # self.clear_kitt_speaking_effect(draw=draw, max_values=max_values, step=i)
    #         self.draw_kitt_speaking_effect_decrease(draw=draw, frame=i)

    #         # We show this row to the device
    #         self.device.display(image)
    #         time.sleep(delay)
    
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
                        self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(0, 3 - y), apply_offset=apply_offset)
                        self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(0, 4 + y), apply_offset=apply_offset)
                        self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(1, 3 - y), apply_offset=apply_offset)
                        self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(1, 4 + y), apply_offset=apply_offset)
                        self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(6, 3 - y), apply_offset=apply_offset)
                        self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(6, 4 + y), apply_offset=apply_offset)
                        self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(7, 3 - y), apply_offset=apply_offset)
                        self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(7, 4 + y), apply_offset=apply_offset)
                elif col_key == "col_4":
                    if col_value > y:
                        # Column 4 and 5
                        self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(3, 3 - y), apply_offset=apply_offset)
                        self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(3, 4 + y), apply_offset=apply_offset)
                        self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(4, 3 - y), apply_offset=apply_offset)
                        self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(4, 4 + y), apply_offset=apply_offset)

    def draw_kitt_speaking_effect(self, draw: ImageDraw.ImageDraw, params: dict):
        """
        Draws the KITT speaking effect on the given canvas, based on the given loop iterations counter and max value.
        It is meant to be called directly from the painting loop, so it can control which frame to draw based on the loop iteration counter.
        """

        current_loop_iteration = params.get("current_loop_iteration", 0)
        max_loop_iterations = params.get("max_loop_iterations", 0)

        frame = current_loop_iteration % (max_loop_iterations // 2)
        if current_loop_iteration < (max_loop_iterations // 2):
            self._log_debug(f"Painter Loop: Drawing Speaking Increase screen on LCD display, frame [{frame}].")
            self._draw_kitt_speaking_effect_increase(draw=draw, frame=frame)
        else:
            self._log_debug(f"Painter Loop: Drawing Speaking Decrease screen on LCD display, frame [{frame}].")
            self._draw_kitt_speaking_effect_decrease(draw=draw, frame=frame)

    def _draw_kitt_speaking_effect_increase(self, draw: ImageDraw.ImageDraw, frame: int = None):
        counter = 0

        # We go row by row from the middle point to the top and bottom extremes
        for drawing_frame in range(1, 5):

            # Every frame needs to be cleared first, to avoid having an effect of overlaying frames
            self.base_frame_for_display_area(draw=draw, params={"display_area": "top_left"})

            # Every iteration here is a full frame to be drawn
            self._draw_kitt_mouth_frame(draw=draw, frame=drawing_frame)
                
            # We count which is the current step for the drawing.
            # If we have reached the frame, we stop drawing more.
            # This way we can flush to the device in the frames we want.
            if frame is not None and counter >= frame:
                return
            else:
                counter += 1
    
    def _draw_kitt_speaking_effect_decrease(self, draw: ImageDraw.ImageDraw, frame: int = None):
        counter = 0

        # We go row by row from the middle point to the top and bottom extremes
        for drawing_frame in range(3, -1, -1):

            # Every frame needs to be cleared first, to avoid having an effect of overlaying frames
            self.base_frame_for_display_area(draw=draw, params={"display_area": "top_left"})

            # Every iteration here is a full frame to be drawn
            self._draw_kitt_mouth_frame(draw=draw, frame=drawing_frame)
                
            # We count which is the current step for the drawing.
            # If we have reached the frame, we stop drawing more.
            # This way we can flush to the device in the frames we want.
            if frame is not None and counter >= frame:
                return
            else:
                counter += 1

    # def show_init_phase(self, phase):

    #     draw = self.canvas.get_canvas(reset_base_image = False)

    #     self.draw_init_phase(draw=draw, phase=phase)

    #     self.device.display(self.canvas.get_image())
    
    def draw_init_phase(self, draw: ImageDraw.ImageDraw, params: dict):

        # Initial Background Paint clear
        self.base_frame_for_display_area(draw=draw, params={"display_area": "top_left"})

        phase = params.get("phase", 0)
        text = params.get("text", None)

        rows = math.floor(phase / 8) + 1
        rows = rows if rows > 1 else 1
        for y in range(0, rows):
            cols = 8 if y < rows - 1 else phase % 8
            for x in range(0, cols):
                self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(x,  y))
    
    # def show_cross(self):
    #     draw = self.canvas.get_canvas(reset_base_image = False)
    #     self.soft_clear_rectangle(draw=draw, display_area="top_left")
        
    #     self.draw_cross(draw=draw)

    #     self.device.display(self.canvas.get_image())
    
    def draw_cross(self, draw: ImageDraw.ImageDraw, params: dict):
        for i in range(0,8):
            self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(i, i))
            self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(i, i))
            self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(7 - i, i))
    
    # def show_interaction_holding_percentage(self, percentage: int):
    #     '''
    #     Shows on the Matrix LED a percentage bar indicating how much time is left
    #     for the user to hold the interaction (i.e., speak).

    #     Args:
    #         percentage: The percentage of time left (0-100).
    #     '''
    #     draw = self.canvas.get_canvas(reset_base_image = False)

    #     self.draw_interaction_holding_percentage(draw=draw, percentage=percentage)

    #     self.device.display(self.canvas.get_image())
    
    def draw_interaction_holding_percentage(self, draw: ImageDraw.ImageDraw, params: dict):
        '''
        Draws on the given canvas a percentage bar indicating how much time is left
        for the user to hold the interaction (i.e., speak).

        Args:
            draw: The canvas to draw on.
            params: A dictionary containing the parameters for the drawing.
                - percentage: The percentage of time left (0-100).
        '''

        percentage = params.get("percentage", 0)

        # Initial Background Paint clear
        self.base_frame_for_display_area(draw=draw, params={"display_area": "top_left"})

        # Calculate how many columns to light up
        columns_to_light = math.ceil((percentage / 100) * 8)
        for x in range(0, columns_to_light):
            self._draw_led_point_over_lcd_canvas(draw=draw, point=Point(x, 7), apply_offset=False)

    def _draw_led_point_over_lcd_canvas(self, draw: ImageDraw.ImageDraw, point: Point, color: str = None, apply_offset: bool = True):
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
        temp_max_x = self.layout_info["relative"]["top_left"].point_2.x
        temp_max_y = self.layout_info["relative"]["top_left"].point_2.y
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
            
        offset_x += self.layout_info["relative"]["top_left"].point_1.x + (padding * 2) + extra_offset_x + 1
        offset_y = self.layout_info["relative"]["top_left"].point_1.y + (padding * 2) + extra_offset_y + 1
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