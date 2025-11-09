from pyxavi import Config, Logger, Dictionary

from pitxu.lib.matrix_led import Max7219
from ..dto import Rectangle, Line, Point, Matrix

from PIL import Image,ImageDraw,ImageFont

import logging

class Macros:

    _config: Config = None
    _logger: logging = None
    _parameters: Dictionary = None

    _max7219: Max7219 = None

    ON: str = "white"
    OFF: str = "black"

    def __init__(self, config: Config, params: Dictionary):
        self._parameters = params
        self._config = config
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()
        self._max7219 = Max7219(config=config, params=params)
    
    def draw_something(self):
        # The resources needed to draw and print into the led matrix will self close
        # At the end of this context. No more worries.
        # TODO: Maybe we'd like to bring the eInk to this approach
        with self._max7219.create_canvas() as draw:
            matrix = Matrix(points=[
                Point(1,1),
                Point(6,1),
                Point(1,6),
                Point(6,6),
            ]).get_points()
            for point in matrix:
                draw.point(point, self.ON)
    