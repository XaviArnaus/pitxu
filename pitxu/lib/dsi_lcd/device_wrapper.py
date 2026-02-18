
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
    DEFAULT_MOCKED_IMAGES_PATH = "mocked/dsi_lcd/"

    path_for_mocked_images: str = None

    device = None

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config, params: Dictionary):
        super(DeviceWrapper, self).init_pyxavi(config=config, params=params)

        if self.is_dsi_allowed():
            from pitxu.lib.dsi_lcd.framebuffer_screen import FramebufferScreen
            self.device = FramebufferScreen(config=config, params=params)

            # brightness = int(config.get("dsi_lcd.brightness", 50))
            # self.device.set_backlight_mode(True)
            # self.device.set_backlight(brightness)
        else:
            import os
            self.path_for_mocked_images = self._xconfig.get("storage.path", self.DEFAULT_STORAGE_PATH) + self.DEFAULT_MOCKED_IMAGES_PATH
            if os.path.exists(self.path_for_mocked_images) == False:
                os.makedirs(self.path_for_mocked_images)

    def display(self, image: Image.Image, partial: bool = True):
        if (self.is_dsi_allowed()):
            self.device.display(image)
        else:
            if (self._xconfig.get("displays.discard_mocked_images", False)):
                self._log_debug("Won't store mocked image due to [displays.discard_mocked_images].")
            else:
                file_path = self.path_for_mocked_images + datetime.now().strftime("%Y%m%d-%H%M%S.%f") + ".png"
                image.save(file_path)
            
            # The latest we always save.
            file_path = self.path_for_mocked_images + "_latest.png"
            image.save(file_path)
    
    def clear(self):
        if (self.is_dsi_allowed()):
            # self.device._reset_lcd() -> Apparently this causes the LCD to stop working.
            self.device.clear()
        else:
            pass
    
    def close(self):
        if (self.is_dsi_allowed()):
            self.device.close()
        else:
            pass
    
    def is_dsi_allowed(self) -> bool:
        import platform

        os = platform.system()        
        if (os.lower() != "linux"):
            self._log_debug("OS is not Linux, auto mocking LCD")
            return False
        if (self._xconfig.get("dsi_lcd.mock", True)):
            self._log_debug("Mocking LCD by Config")
            return False
        return True