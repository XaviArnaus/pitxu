from pyxavi import Config, Logger, Dictionary

from pitxu.lib.matrix_led import Max7219, HandableCanvas, HandableEmulatedCanvas
from ..objects import Rectangle, Line, Point, Matrix

from PIL import Image,ImageDraw,ImageFont

import logging, time, math

class Macros:
    '''
    Class that builds higher level macros to draw on the Matrix LED display

    Remember that the LED Matrix is 8x8 pixels, (0,0) is top-left and (7,7) is bottom-right
    '''

    _xconfig: Config = None
    _xlog: logging = None
    _xparams: Dictionary = None

    _max7219: Max7219 = None

    _handable_canvas: HandableCanvas | HandableEmulatedCanvas = None

    ON: str = "white"
    OFF: str = "black"

    def __init__(self, config: Config, params: Dictionary):
        self._xparams = params
        self._xconfig = config
        self._xlog = Logger(config=config, base_path=self._xparams.get("base_path", "")).get_logger()
        # self._max7219 = Max7219(config=config, params=params)
        self._max7219 = params.get("matrix_device")
    
    def draw_something(self):
        # The resources needed to draw and print into the led matrix will self close
        # At the end of this context. No more worries.
        # TODO: Maybe we'd like to bring the eInk to this approach
        self._xlog.debug("Starting the drawing")
        with self._max7219.create_canvas() as draw:
            matrix = Matrix(points=[
                Point(1,1),
                Point(6,1),
                Point(1,6),
                Point(6,6),
            ]).get_points()
            for point in matrix:
                self._xlog.debug("Drawing point: " + str(point))
                draw.point(point.to_image_point(), self.ON)

            # Script of points
            # do_something = []
            # for i in range(0,7,1):
            #     for j in range(0,7,1):
            #         do_something.append(Point(i,j))
            # for point in do_something:
            #     self._xlog.debug("Drawing point: " + str(point))
            #     draw.point(point.to_image_point(), self.ON)
            #     time.sleep(0.1)
    
    def kitt_horizontal_effect(self, delay: float = 0.1):
        self._xlog.debug("Starting KITT effect")

        canvas = self._handable_canvas.get()
        canvas.rectangle((0,0,7,7), self.OFF)

        # Move right
        for x in range(8):
            canvas.rectangle((0,0,7,7), self.OFF)
            canvas.point((x,3), self.ON)
            canvas.point((x,4), self.ON)
            self._handable_canvas.send_to_device()
            time.sleep(delay)
        # Move left
        for x in range(6,-1,-1):
            canvas.rectangle((0,0,7,7), self.OFF)
            canvas.point((x,3), self.ON)
            canvas.point((x,4), self.ON)
            self._handable_canvas.send_to_device()
            time.sleep(delay)
    
    def open_canvas(self) -> HandableCanvas:
        if self._handable_canvas is None:
            self._xlog.debug("Opening Handable Canvas")
            self._handable_canvas = self._max7219.create_handable_canvas()
        return self._handable_canvas
    
    def close_canvas(self):
        if self._handable_canvas is not None:
            # Most likely we don't want to show anything else
            # So we simply set up a black image
            if self._handable_canvas.draw is not None:
                self._handable_canvas.draw.rectangle((0,0,7,7), self.OFF)
            self._handable_canvas.close()
            self._handable_canvas = None
    
    def kitt_speaking_effect_vu_meter(self, col_1: int, col_2: int, col_3: int, col_4: int, delay: float = 0.03):
        '''
        KITT speaking effect using VU Meter columns

        Be careful, it relies on having a HandableCanvas instance opened previously, and
        needs to be closed afterwards.
        '''
        canvas = self._handable_canvas.get()
        canvas.rectangle((0,0,7,7), self.OFF)

        max_values = {
            # "col_1": col_1,
            "col_2": col_2,
            "col_3": col_3,
            "col_4": col_4,
        }

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
                        canvas.point((0, 3 - y), self.ON)
                        canvas.point((0, 4 + y), self.ON)
                        canvas.point((1, 3 - y), self.ON)
                        canvas.point((1, 4 + y), self.ON)
                        canvas.point((6, 3 - y), self.ON)
                        canvas.point((6, 4 + y), self.ON)
                        canvas.point((7, 3 - y), self.ON)
                        canvas.point((7, 4 + y), self.ON)
                    elif col_key == "col_4":
                        # Column 4 and 5
                        canvas.point((3, 3 - y), self.ON)
                        canvas.point((3, 4 + y), self.ON)
                        canvas.point((4, 3 - y), self.ON)
                        canvas.point((4, 4 + y), self.ON)
            
            # We show this row to the device
            self._handable_canvas.send_to_device()
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
                        canvas.point((0, 3 - y), self.OFF)
                        canvas.point((0, 4 + y), self.OFF)
                        canvas.point((1, 3 - y), self.OFF)
                        canvas.point((1, 4 + y), self.OFF)
                        canvas.point((6, 3 - y), self.OFF)
                        canvas.point((6, 4 + y), self.OFF)
                        canvas.point((7, 3 - y), self.OFF)
                        canvas.point((7, 4 + y), self.OFF)
                    elif col_key == "col_4":
                        # Column 4 and 5
                        canvas.point((3, 3 - y), self.OFF)
                        canvas.point((3, 4 + y), self.OFF)
                        canvas.point((4, 3 - y), self.OFF)
                        canvas.point((4, 4 + y), self.OFF)
            
            # We show this row to the device
            self._handable_canvas.send_to_device()
            time.sleep(delay)

    def show_init_step(self, step):

        with self._max7219.create_canvas() as canvas:
            rows = math.floor(step / 8)
            rows = rows if rows > 0 else 0
            for y in range(0, rows + 1):
                for x in range(0, step % 7 + 1):
                    self._xlog.debug(f"Showing init step point at ({x},{y})")
                    canvas.point((x, y), self.ON)
    
    def show_cross(self):
        canvas = self._handable_canvas.get()
        canvas.rectangle((0,0,7,7), self.OFF)
        for i in range(0,8):
            canvas.point((i,i), self.ON)
            canvas.point((7 - i,i), self.ON)
        self._handable_canvas.send_to_device()