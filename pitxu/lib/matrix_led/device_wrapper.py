
import time
import logging

from pyxavi import Config, Logger, Dictionary

from luma.led_matrix.device import max7219

class DeviceWrapper(max7219):
    '''
    Wrapper for the device's class in order to apply emulation if required.
    '''

    _parameters: Dictionary = None
    _config: Config = None
    _logger: logging = None

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_MOCKED_IMAGES_PATH = "mocked/matrix/"

    def __init__(self, config: Config, params: Dictionary, serial_interface = None):
        self._config = config
        self._parameters = params
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()

        if self.is_spi_allowed():
            super(DeviceWrapper, self).__init__(serial_interface=serial_interface)

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