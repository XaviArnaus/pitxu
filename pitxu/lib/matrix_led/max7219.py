import os
import logging

from pyxavi import Config, Logger, Dictionary
from pitxu.lib.objects import Point, Rectangle, Matrix
from . import EmulatedCanvas, DeviceWrapper

from luma.core.interface.serial import spi, noop
from luma.core.render import canvas

from PIL import ImageDraw,ImageFont


class Max7219:
    '''
    https://luma-led-matrix.readthedocs.io/en/latest/python-usage.html
    '''

    _xparams: Dictionary = None
    _xconfig: Config = None
    _xlog: logging = None

    _serial: spi = None
    _device: DeviceWrapper = None

    FONT: ImageFont = None

    EMULATION_MODE: str = None
    EMULATION_SIZE: tuple = None

    BOUNDING_BOX: tuple = None

    ON: str = "white"    # This is an LED ON
    OFF: str = "black"    # This is an LED OFF

    def __init__(self, config: Config, params: Dictionary):
        # Never use the property `.bounding_box` from the emulated canvas

        # Possible runtime parameters
        self._xparams = params

        # Config is mandatory
        if config is None:
            raise RuntimeError("Config can not be None")
        self._xconfig = config

        # Common Logger
        self._xlog = Logger(config=config, base_path=self._xparams.get("base_path", "")).get_logger()

        # Max7219
        if (not self._xconfig.get("matrix_led.mock", True)):
            self._serial = spi(port=0, device=0, gpio=noop())
        self._device = DeviceWrapper(config=config, params=params, serial_interface=self._serial)
        self._device.clear()
        self._device.contrast(int(config.get("matrix_led.intensity", 100)))
        self.EMULATION_MODE = "1"
        self.EMULATION_SIZE = Point(
            self._xconfig.get("matrix_led.size.x", 8) - 1,
            self._xconfig.get("matrix_led.size.y", 8) - 1
        ).to_image_point()
        self.BOUNDING_BOX = Rectangle(
            Point(0,0),
            Point(
                self._xconfig.get("matrix_led.size.x", 8) - 1,
                self._xconfig.get("matrix_led.size.y", 8) - 1
            )
        ).to_image_rectangle()

        font_path = os.path.join(self._xparams.get("base_path", ""), 'pitxu', 'lib', 'fonts', 'matrix')
        self.FONT = ImageFont.truetype(os.path.join(font_path, 'pixelmix.ttf'), 8)
    
    def get_device(self) -> DeviceWrapper:
        if self._device is not None:
            return self._device
        else:
            raise RuntimeError("The LED Matrix device is not initialised")
    
    def create_canvas(self) -> canvas:
        if (self._xconfig.get("matrix_led.mock", True)):
            self._xlog.debug("Creating Matrix Emulation Canvas")
            return EmulatedCanvas(self._xconfig, self._xparams, self.EMULATION_MODE, self.EMULATION_SIZE)
        else:
            self._xlog.debug("Creating Matrix Canvas")
            return canvas(self._device)
    
    def clear(self, draw: ImageDraw = None) -> None:
        self._xlog.debug("Clearing Matrix.")
        if draw:
            draw.rectangle(self.BOUNDING_BOX, outline=self.OFF, fill=self.OFF)
        else:
            with self.create_canvas() as draw:
                self._xlog.debug("The rectangle size is " + str(self.BOUNDING_BOX))
                draw.rectangle(self.BOUNDING_BOX, outline=self.OFF, fill=self.OFF)
    
    def draw(self, list_of_activated_leds: list[Point] = []) -> None:        
        with self.create_canvas() as draw:
            # First we clear the matrix
            self.clear(draw=draw)
            # Now we just activate leds via the given Points
            self._xlog.debug("Drawing arbitrary points: " + str(list_of_activated_leds))
            for point in list_of_activated_leds:
                draw.point(point.to_image_point(), fill=self.ON)
    
    def test(self):
        # Manually define the leds to light up
        self._xlog.debug("Showing a test matrix")
        matrix = Matrix(points=[
            Point(1,1),
            Point(6,1),
            Point(1,6),
            Point(6,6),
        ])
        self.draw(matrix.get_points())


            