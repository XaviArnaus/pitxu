
import time
import logging

from pyxavi import Config, Logger, Dictionary

from luma.led_matrix.device import max7219
from PIL import ImageDraw
import luma.core.const

class DeviceWrapper(max7219):
    '''
    Wrapper for the device's class in order to apply emulation if required.
    '''

    _xparams: Dictionary = None
    _xconfig: Config = None
    _xlog: logging = None

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_MOCKED_IMAGES_PATH = "mocked/matrix/"

    def __init__(self, config: Config, params: Dictionary, serial_interface = None, contrast=None):
        self._xconfig = config
        self._xparams = params
        self._xlog = Logger(config=config, base_path=self._xparams.get("base_path", "")).get_logger()
        if contrast is None:
                contrast = int(config.get("matrix_led.intensity", 150))

        if self.is_spi_allowed():
            super(DeviceWrapper, self).__init__(serial_interface=serial_interface, contrast=contrast)
        else:
            self._const = luma.core.const.common
            self.cascaded = 1
            self._const.INTENSITY = contrast

    def display(self, image: ImageDraw):
        if (self.is_spi_allowed()):
            super(DeviceWrapper, self).display(image)
        else:
            file_path = self._xconfig.get("storage.path", self.DEFAULT_STORAGE_PATH) + self.DEFAULT_MOCKED_IMAGES_PATH + time.strftime("%Y%m%d-%H%M%S") + ".png"
            image.save(file_path)
            file_path = self._xconfig.get("storage.path", self.DEFAULT_STORAGE_PATH) + self.DEFAULT_MOCKED_IMAGES_PATH + "_latest.png"
            image.save(file_path)
    
    def clear(self):
        if (self.is_spi_allowed()):
            super(DeviceWrapper, self).clear()
        else:
            pass
    
    def data(self, data):
        if (self.is_spi_allowed()):
            super(DeviceWrapper, self).data(data)
        else:
            pass
    
    def is_spi_allowed(self) -> bool:
        import platform

        os = platform.system()        
        if (os.lower() != "linux"):
            self._xlog.warning("OS is not Linux, auto mocking LED Matrix")
            return False
        if (self._xconfig.get("matrix_led.mock", True)):
            self._xlog.warning("Mocking LED Matrix by Config")
            return False
        return True