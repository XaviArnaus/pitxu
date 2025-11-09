from pyxavi import Config, Logger, Dictionary

from pitxu.lib.matrix_led import Max7219
from ..dto import Rectangle, Line, Point

from PIL import Image,ImageDraw,ImageFont

import logging

class Macros:

    _config: Config = None
    _logger: logging = None
    _parameters: Dictionary = None

    _max7219: Max7219 = None

    WHITE: str = "white"
    BLACK: str = "black"

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
            # draw.rectangle(Point(
            #     self._config.get("matrix_led.size.x", 8),
            #     self._config.get("matrix_led.size.y", 8)
            # ).to_image_point(), outline="white", fill="black")
            draw.point(Point(0,0).to_image_point(), self.BLACK)
    