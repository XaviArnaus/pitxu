from pyxavi import Config, Logger, Dictionary

from pitxu.lib.matrix_led import Max7219, HandableCanvas, HandableEmulatedCanvas
from ..objects import Rectangle, Line, Point, Matrix

from PIL import Image,ImageDraw,ImageFont

import logging, time

class Macros:

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
    
    def kitt_horizontal_effect(self, iterations: int = 5, delay: float = 0.1):
        self._xlog.debug("Starting KITT effect")
        with self._max7219.create_canvas() as draw:
            for _ in range(iterations):
                # Move right
                for x in range(8):
                    draw.rectangle((0,0,7,7), self.OFF)
                    draw.point((x,3), self.ON)
                    time.sleep(delay)
                # Move left
                for x in range(6,-1,-1):
                    draw.rectangle((0,0,7,7), self.OFF)
                    draw.point((x,3), self.ON)
                    time.sleep(delay)
    
    def kitt_speaking_effect(self, delay: float = 0.1):
        '''
        KITT speaking effect: a line moving up and down in the middle of the matrix

        Be careful, it relies on having a HandableCanvas instance opened previously, and
        needs to be closed afterwards.
        '''
        self._xlog.debug("Starting KITT speaking effect")

        canvas = self._handable_canvas.get()
        mid_y = 3
        # Move up
        for y in range(mid_y, -1, -1):
            canvas.rectangle((0,0,7,7), self.OFF)
            canvas.line((0, y, 7, y), self.ON)
            self._handable_canvas.send_to_device()
            time.sleep(delay)
        # Move down
        for y in range(1, mid_y + 1):
            canvas.rectangle((0,0,7,7), self.OFF)
            canvas.line((0, y, 7, y), self.ON)
            self._handable_canvas.send_to_device()
            time.sleep(delay)
    
    def open_canvas(self) -> HandableCanvas:
        if self._handable_canvas is None:
            self._xlog.debug("Opening Handable Canvas")
            self._handable_canvas = self._max7219.create_handable_canvas()
        return self._handable_canvas
    
    def close_canvas(self):
        if self._handable_canvas is not None:
            self._handable_canvas.close()
            self._handable_canvas = None
    
    def kitt_speaking_effect_vu_meter(self, col_1: int, col_2: int, col_3: int, col_4: int, delay: float = 0.1):
        '''
        KITT speaking effect using VU Meter columns

        Be careful, it relies on having a HandableCanvas instance opened previously, and
        needs to be closed afterwards.
        '''
        self._xlog.debug("Starting KITT speaking effect VU Meter")

        canvas = self._handable_canvas.get()
        canvas.rectangle((0,0,7,7), self.OFF)

        # Column 1 and 7
        for y in range(0, col_1):
            # North rows
            canvas.point((0, 3 - y), self.ON)
            canvas.point((7, 3 - y), self.ON)
            # South rows
            canvas.point((0, 4 + y), self.ON)
            canvas.point((7, 4 + y), self.ON)
        
        # Column 2 and 6
        for y in range(0, col_2):
            # North rows
            canvas.point((1, 3 - y), self.ON)
            canvas.point((6, 3 - y), self.ON)
            # South rows
            canvas.point((1, 4 + y), self.ON)
            canvas.point((6, 4 + y), self.ON)
        
        # Column 3 and 5
        for y in range(0, col_3):
            # North rows
            canvas.point((2, 3 - y), self.ON)
            canvas.point((5, 3 - y), self.ON)
            # South rows
            canvas.point((2, 4 + y), self.ON)
            canvas.point((5, 4 + y), self.ON)
        
        # Column 4 and 4
        for y in range(0, col_4):
            # North rows
            canvas.point((3, 3 - y), self.ON)
            canvas.point((4, 3 - y), self.ON)
            # South rows
            canvas.point((3, 4 + y), self.ON)
            canvas.point((4, 4 + y), self.ON)
        
        self._handable_canvas.send_to_device()
        time.sleep(delay)

    
    