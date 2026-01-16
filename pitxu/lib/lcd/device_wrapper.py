
import time
import logging

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.device import Device
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.lcd_kleine.mocked_ST7789 import MockedST7789

from PIL import Image

class DeviceWrapper(PyXavi, Device):
    '''
    Wrapper for the device's class in order to apply emulation if required.
    '''

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_MOCKED_IMAGES_PATH = "mocked/lcd/"

    DEVICE = {
        "SPI_BUS": 0,
        "SPI_DEVICE": 0,
        "RST_PIN": 7,
        "DC_PIN": 13,
        "BL_PIN": 15,
        "BRIGHTNESS": 100,
        "WIDTH": 280,
        "HEIGHT": 240
    }

    path_for_mocked_images: str = None

    driver: MockedST7789 = None

    def __init__(self, config: Config, params: Dictionary):
        super(DeviceWrapper, self).init_pyxavi(config=config, params=params)

        if self.is_spi_allowed():
            from pitxu.lib.lcd_kleine.ST7789 import ST7789

            spi_bus = self._xconfig.get("lcd.hardware.bus", self.DEVICE["SPI_BUS"])
            spi_device = self._xconfig.get("lcd.hardware.device", self.DEVICE["SPI_DEVICE"])
            rst = self._xconfig.get("lcd.hardware.RST", self.DEVICE["RST_PIN"])
            dc = self._xconfig.get("lcd.hardware.DC", self.DEVICE["DC_PIN"])
            bl = self._xconfig.get("lcd.hardware.BL", self.DEVICE["BL_PIN"])

            self._xlog.debug(f"SPI Bus={spi_bus}, Device={spi_device}")
            self._xlog.debug(f"GPIO RST={rst}, DC={dc}, BL={bl}")
            self.driver = ST7789(
                spi_bus=spi_bus,
                spi_device=spi_device,
                rst=rst,
                dc=dc,
                bl=bl
            )
            # Initialize library.
            self.driver.Init()
            # Clear display.
            self.driver.clear()
            #Set the backlight to 100
            self.driver.bl_DutyCycle(self._xconfig.get("lcd.hardware.brightness", self.DEVICE["BRIGHTNESS"]))
            
            # from pitxu.lib.lcd.st7789 import ST7789
            # self.driver = ST7789(config=config, params=params)

            # brightness = int(config.get("lcd.brightness", 50))
            # self.driver.set_backlight_mode(True)
            # self.driver.set_backlight(brightness)
        else:
            import os
            self.path_for_mocked_images = self._xconfig.get("storage.path", self.DEFAULT_STORAGE_PATH) + self.DEFAULT_MOCKED_IMAGES_PATH
            if os.path.exists(self.path_for_mocked_images) == False:
                os.makedirs(self.path_for_mocked_images)

    def display(self, image: Image.Image, partial: bool = True):
        if (self.is_spi_allowed()):
            # self.driver.draw_image(
            #     0, 0, self.device.LCD_WIDTH, self.device.LCD_HEIGHT,
            #     bytearray(image.tobytes()))
            self.driver.ShowImage(image)
        else:
            file_path = self.path_for_mocked_images + time.strftime("%Y%m%d-%H%M%S") + ".png"
            image.save(file_path)
            file_path = self.path_for_mocked_images + "_latest.png"
            image.save(file_path)
    
    def clear(self):
        if (self.is_spi_allowed()):
            # self.driver._reset_lcd()
            self.driver.clear()
        else:
            pass
    
    def is_spi_allowed(self) -> bool:
        import platform

        os = platform.system()        
        if (os.lower() != "linux"):
            self._xlog.debug("OS is not Linux, auto mocking LCD")
            return False
        if (self._xconfig.get("lcd.mock", True)):
            self._xlog.debug("Mocking LCD by Config")
            return False
        return True