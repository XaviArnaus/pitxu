
import os
import time
import logging

from pyxavi import Config, Logger, Dictionary
from pitxu.lib.dto import Point, Rectangle
from . import EmulatedCanvas

from luma.core.interface.serial import spi, noop
from luma.core.render import canvas
from luma.led_matrix.device import max7219

from PIL import Image,ImageDraw,ImageFont

class DeviceWrapper(max7219):
    '''
    Wrapper for the device's class in order to apply emulation if required.
    '''

    _parameters: Dictionary = None
    _config: Config = None
    _logger: logging = None

    _local_bounding_box: tuple = None

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_MOCKED_IMAGES_PATH = "mocked/matrix/"

    def __init__(self, config: Config, params: Dictionary, serial_interface = None):
        self._config = config
        self._parameters = params
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()

        if self.is_spi_allowed():
            super(DeviceWrapper, self).__init__(serial_interface=serial_interface)
        else:
            self._local_bounding_box = (0, 0, 7, 7)
    
    # @property
    # def bounding_box(self):
    #     if (self.is_spi_allowed()):
    #         return super(DeviceWrapper, self).bounding_box
    #     else:
    #         return self._local_bounding_box
    
    # @bounding_box.setter
    # def bounding_box(self, value: tuple):
    #     if (self.is_spi_allowed()):
    #         super(DeviceWrapper, self).bounding_box = value
    #     else:
    #         self._local_bounding_box = value

    def display(self, image):
        if (self.is_spi_allowed()):
            super(DeviceWrapper, self).display(image)
        else:
            file_path = self._config.get("storage.path", self.DEFAULT_STORAGE_PATH) + self.DEFAULT_MOCKED_IMAGES_PATH + time.strftime("%Y%m%d-%H%M%S") + ".png"
            image.save(file_path)
            file_path = self._config.get("storage.path", self.DEFAULT_STORAGE_PATH) + self.DEFAULT_MOCKED_IMAGES_PATH + "_latest.png"
            image.save(file_path)
    
    def is_spi_allowed(self) -> bool:
        import platform

        os = platform.system()        
        if (os.lower() != "linux"):
            self._logger.warning("OS is not Linux, auto mocking LED Matrix")
            return False
        if (self._config.get("matrix_led.mock", True)):
            self._logger.warning("Mocking LED Matrix by Config")
            return False
        return True
        

class Max7219:
    '''
    https://luma-led-matrix.readthedocs.io/en/latest/python-usage.html
    '''

    _parameters: Dictionary = None
    _config: Config = None
    _logger: logging = None

    _serial: spi = None
    _device: DeviceWrapper = None

    FONT: ImageFont = None

    EMULATION_MODE: str = None
    EMULATION_SIZE: tuple = None

    BOUNDING_BOX: tuple = None

    WHITE: str = "white"
    BLACK: str = "black"

    def __init__(self, config: Config, params: Dictionary):
        # Never use the property `.bounding_box` from the emulated canvas

        # Possible runtime parameters
        self._parameters = params

        # Config is mandatory
        if config is None:
            raise RuntimeError("Config can not be None")
        self._config = config

        # Common Logger
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()

        # Max7219
        if (not self._config.get("matrix_led.mock", True)):
            self._serial = spi(port=0, device=0, gpio=noop())
        self._device = DeviceWrapper(config=config, params=params, serial_interface=self._serial)
        self.EMULATION_MODE = "1"
        self.EMULATION_SIZE = Point(
            self._config.get("matrix_led.size.x", 8),
            self._config.get("matrix_led.size.y", 8)
        ).to_image_point()
        self.BOUNDING_BOX = Rectangle(
            Point(0,0),
            Point(
                self._config.get("matrix_led.size.x", 8),
                self._config.get("matrix_led.size.y", 8)
            )
        ).to_image_rectangle()

        font_path = os.path.join(self._parameters.get("base_path", ""), 'pitxu', 'lib', 'fonts', 'matrix')
        self.FONT = ImageFont.truetype(os.path.join(font_path, 'pixelmix.ttf'), 8)
    
    def get_device(self) -> DeviceWrapper:
        if self._device is not None:
            return self._device
        else:
            raise RuntimeError("The LED Matrix device is not initialised")
    
    def create_canvas(self) -> canvas:
        if (self._config.get("matrix_led.mock", True)):
            self._logger.debug("Creating Matrix Emulation Canvas")
            return EmulatedCanvas(self._config, self._parameters, self.EMULATION_MODE, self.EMULATION_SIZE)
        else:
            self._logger.debug("Creating Matrix Canvas")
            return canvas(self._device)
    
    def clear(self, draw: ImageDraw = None) -> None:
        self._logger.debug("Clearing Matrix.")
        if draw:
            draw.rectangle(self.BOUNDING_BOX, outline=self.WHITE, fill=self.WHITE)
        else:
            with self.create_canvas() as draw:
                self._logger.debug("The rectangle size is " + str(self.BOUNDING_BOX))
                draw.rectangle(self.BOUNDING_BOX, outline=self.WHITE, fill=self.WHITE)
    
    def draw(self, list_of_activated_leds: list[Point] = []) -> None:        
        with self.create_canvas() as draw:
            # First we clear the matrix
            self.clear(draw=draw)
            # Now we just activate all leds via the given Points
            for point in list_of_activated_leds:
                draw.point(point.to_image_point(), fill=self.BLACK)
    
    def test(self):
        # Manually define the leds to light up
        self._logger.debug("Showing a test matrix")
        self.draw([
            Point(1,1),
            Point(3,1),
            Point(5,1),
            Point(7,1),
            Point(1,3),
            Point(3,3),
            Point(5,3),
            Point(7,3),
            Point(1,5),
            Point(3,5),
            Point(5,5),
            Point(7,5),
            Point(1,7),
            Point(3,7),
            Point(5,7),
            Point(7,7),
        ])


            