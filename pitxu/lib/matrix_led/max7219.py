
import os
import time
import logging

from pyxavi import Config, Logger, Dictionary
from pitxu.lib.dto import Point
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

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_MOCKED_IMAGES_PATH = "mocked/matrix/"

    def __init__(self, config: Config, params: Dictionary, **kwargs):
        super(DeviceWrapper, self).__init__(kwargs=kwargs)

        self._config = config
        self._parameters = params
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()
    
    @property
    def bounding_box(self):
        if (self.is_spi_allowed()):
            return super(DeviceWrapper, self).bounding_box
        else:
            # return (0, 0, self.width - 1, self.height - 1)
            return (0, 0, 7, 7)

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

    def __init__(self, config: Config, params: Dictionary):

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
            self._device = DeviceWrapper(self._serial)
        self.EMULATION_MODE = "1"
        self.EMULATION_SIZE = Point(8,8).to_image_point()

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
            return EmulatedCanvas(self._config, self.EMULATION_MODE, self.EMULATION_SIZE)
        else:
            self._logger.debug("Creating Matrix Canvas")
            return canvas(self._device)
            