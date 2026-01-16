import os
import time
import logging
import platform
from .mocked_ST7789 import MockedST7789
from PIL import Image,ImageDraw,ImageFont

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.objects.point import Point

from definitions import ROOT_DIR

class Lcd(PyXavi):

    DEVICE = {
        "SPI_BUS": 0,
        "SPI_DEVICE": 0,
        "RST_PIN": 27,
        "DC_PIN": 25,
        "BL_PIN": 12,
        "BRIGHTNESS": 255,
        "WIDTH": 280,
        "HEIGHT": 240
    }

    # We use the MockedST7789 as the type for the driver,
    # even if in real use it will be the ST7789 class
    # This is to avoid import issues on non-Linux platforms
    driver: MockedST7789 = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Lcd, self).init_pyxavi(config=config, params=params)

        # Initialise the LCD display
        self._xlog.info("Initialising LCD display...")
        self.driver = self.get_driver()

    def get_driver(self) -> MockedST7789:
        """
        Get the LCD driver instance as a singleton
        """
        if self.driver is None:

            # In case we need to mock, use the mocked driver
            if platform.system() != "Linux" or self._xconfig.get("lcd.mock", False):
                self._xlog.warning("Using Mocked ST7789 LCD driver")
                self.driver = MockedST7789(config=self._xconfig, params=Dictionary({
                    "width": self._xconfig.get("lcd.size.x"),
                    "height": self._xconfig.get("lcd.size.y")
                }))
                return self.driver

            # Still here? Use the real driver
            self._xlog.info("Using real ST7789 LCD driver")
            from .ST7789 import ST7789

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
        return self.driver

    def get_screen_size(self) -> Point:
        """
        Get the screen size as a tuple (width, height)
        """
        return Point(self.driver.width, self.driver.height)

    def flush_to_device(self, image: Image.Image):
        if self._xconfig.get("lcd.rotate", False):
                # In the test example it is rotated 180 degrees before ShowImage
                image = image.rotate(180)
        self.driver.ShowImage(image)
    
    def clear(self):
        """
        Clear the LCD display
        """
        self.driver.clear()
    
    def close(self):
        """
        Close the LCD display
        """
        self.driver.module_exit()