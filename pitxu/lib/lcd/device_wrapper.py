
from datetime import datetime
import logging

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.device import Device
from pitxu.lib.abstract.pyxavi import PyXavi

from PIL import Image

class DeviceWrapper(PyXavi, Device):
    '''
    Wrapper for the device's class in order to apply emulation if required.
    '''

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_MOCKED_IMAGES_PATH = "mocked/lcd/"

    path_for_mocked_images: str = None

    device = None

    def __init__(self, config: Config, params: Dictionary):
        super(DeviceWrapper, self).init_pyxavi(config=config, params=params)

        if self.is_spi_allowed():
            from pitxu.lib.lcd.st7789 import ST7789
            self.device = ST7789(config=config, params=params)

            brightness = int(config.get("lcd.brightness", 50))
            self.device.set_backlight_mode(True)
            self.device.set_backlight(brightness)
        else:
            import os
            self.path_for_mocked_images = self._xconfig.get("storage.path", self.DEFAULT_STORAGE_PATH) + self.DEFAULT_MOCKED_IMAGES_PATH
            if os.path.exists(self.path_for_mocked_images) == False:
                os.makedirs(self.path_for_mocked_images)

    def display(self, image: Image.Image, partial: bool = True):
        if (self.is_spi_allowed()):
            self.device.draw_image(image)
        else:
            file_path = self.path_for_mocked_images + datetime.now().strftime("%Y%m%d-%H%M%S.%f") + ".png"
            image.save(file_path)
            file_path = self.path_for_mocked_images + "_latest.png"
            image.save(file_path)
    
    def clear(self):
        if (self.is_spi_allowed()):
            # self.device._reset_lcd() -> Apparently this causes the LCD to stop working.
            self.device.clear()
        else:
            pass
    
    def is_spi_allowed(self) -> bool:
        import platform

        os = platform.system()        
        if (os.lower() != "linux"):
            self._log_debug("OS is not Linux, auto mocking LCD")
            return False
        if (self._xconfig.get("lcd.mock", True)):
            self._log_debug("Mocking LCD by Config")
            return False
        return True