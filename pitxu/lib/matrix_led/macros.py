from pyxavi import Config, Logger, Dictionary

from pitxu.lib.matrix_led import Max7219
from ..objects import Rectangle, Line, Point, Matrix

from PIL import Image,ImageDraw,ImageFont

import logging, time

class Macros:

    _xconfig: Config = None
    _xlog: logging = None
    _xparams: Dictionary = None

    _max7219: Max7219 = None

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
    