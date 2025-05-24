import sys
import os
import logging
import time

# # Lib should be in the sys path
# picdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'pic')
# libdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'lib')
# print("Lib dir is " + libdir)
# if os.path.exists(libdir):
#     sys.path.append(libdir)
# else:
#     print("lib does not exists")

# from ..waveshare_epd import epd2in13_V4

from PIL import Image,ImageDraw,ImageFont

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary

from ..dto.point import Point

class EinkDisplay:

    _epd = None
    _parameters: Dictionary = None
    _config: Config = None
    _logger: logging = None
    _font_big = None
    _font_medium = None
    _font_small = None
    _pic_dir: str = None
    _working_image = None
    _screen_size: Point = None

    DEFAULT_FONT_BIG_SIZE = 24
    DEFAULT_FONT_MEDIUM_SIZE = 20
    DEFAULT_FONT_SMALL_SIZE = 15

    def __init__(self, config: Config = None, params: Dictionary = None):

        # Possible runtime parameters
        self._parameters = params

        # Config is mandatory
        if config is None:
            raise RuntimeError("Config can not be None")
        self._config = config

        # Common Logger
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()
        
        # Initialise the display
        self._initialise_display()

        # Initialise fonts
        self._initialise_fonts()
    
    def create_canvas(self):
        image = self._get_image(True)
        return ImageDraw.Draw(image)
    
    def display(self):
        if (not self._is_gpio_allowed()):
            file_path = self._config.get("storage.path") + "mocked/" + time.strftime("%Y%m%d-%H%M%S") + ".png"
            self._working_image.save(file_path)
        else:
            self._epd.display(self._epd.getbuffer(self._working_image))
    
    def clear(self):
        if (self._is_gpio_allowed()):
            self._epd.Clear(0xFF)
        else:
            pass
    
    def test(self):
        logging.info("Drawing on the image...")
        draw = self.create_canvas()
        draw.rectangle([(0,0),(50,50)],outline = 0)
        draw.rectangle([(55,0),(100,50)],fill = 0)
        draw.line([(0,0),(50,50)], fill = 0,width = 1)
        draw.line([(0,50),(50,0)], fill = 0,width = 1)
        draw.chord((10, 60, 50, 100), 0, 360, fill = 0)
        draw.ellipse((55, 60, 95, 100), outline = 0)
        draw.pieslice((55, 60, 95, 100), 90, 180, outline = 0)
        draw.pieslice((55, 60, 95, 100), 270, 360, fill = 0)
        draw.polygon([(110,0),(110,50),(150,25)],outline = 0)
        draw.polygon([(190,0),(190,50),(150,25)],fill = 0)
        draw.text((120, 60), 'e-Paper demo', font = self._font_small, fill = 0)
        draw.text((110, 90), u'微雪电子', font = self._font_big, fill = 0)
        # image = image.rotate(180) # rotate
        self.display()
        time.sleep(2)
        self.clear()
        time.sleep(2)
    
    def _get_image(self, clear_background: bool = True):
        """
        Returns the image that is being prepared to show

        If does not exists, creates it.
        """
        if self._working_image is None:
            self._working_image = Image.new('1', (self._screen_size.x, self._screen_size.y), 255 if clear_background else 0)
            # if (not self._is_gpio_allowed()):
            #     timestamp = time.strftime("%Y%m%d-%H%M%S")
            #     self._working_image = Image.open(self._config.get("storage.path") + "mocked/" + timestamp + ".png")
            # else:
                
        return self._working_image
    
    def _is_gpio_allowed(self):
        import platform

        os = platform.system()        
        if (os.lower() != "linux"):
            self._logger.warning("OS is not Linux, auto mocking eInk")
            return False
        if (self._config.get("display.mock", True)):
            self._logger.warning("Mocking eInk by Config")
            return False
        return True
        
    
    def _initialise_display(self):
        """
        Initialisation of the actual e-Ink controller

        As it uses internal compiled source, it needs the real path to be added into the system lookup paths.
        Once it is loaded, the controller stays instantiated in the class, so it's fine to have it imported
        here locally if we expose the instance afterwards.
        """

        # Initialise the paths
        self._pic_dir = os.path.join(self._parameters.get("base_path", ""), 'pitxu', 'pic')
        libdir = os.path.join(self._parameters.get("base_path", ""), 'pitxu', 'lib')

        # Don't initialise if not allowed
        if (not self._is_gpio_allowed()):
            # Setup base data
            self._screen_size = Point(self._config.get("display.size.x"), self._config.get("display.size.y"))
            self._logger.warning("GPIO is not allowed, avoiding initializing eInk")
            return

        # Lib should be in the sys path
        self._logger.debug("Trying to load the lib directory at: " + libdir)
        if os.path.exists(libdir):
            sys.path.append(libdir)
        else:
            self._logger.warning("Could not find the lib directory at: " + libdir)
            print("lib does not exists")
        from waveshare_epd.epd2in13_V4 import EPD

        # Initialise the display controller
        self._logger.debug("Initialising eInk controller")
        self._epd = EPD()

        # Initialise the display itself
        self._logger.debug("Initialising eInk display")
        self._epd.init()
        self._logger.debug("Cleaning for the first time")
        self._epd.Clear(0xFF)

        # Setup base data
        self._screen_size = Point(self._epd.width, self._epd.height)
    
    def _initialise_fonts(self):
        """
        Initialise the fonts BIG, MEDIUM and SMALL.
        Priority is:
        - Params: in case we have runtime values
        - Config: to use the overall app setup
        - Class default: Fonts must exist, so this is the last resort
        """
        big_size = self.DEFAULT_FONT_BIG_SIZE
        medium_size = self.DEFAULT_FONT_MEDIUM_SIZE
        small_size = self.DEFAULT_FONT_SMALL_SIZE

        # Big size
        if (self._parameters.key_exists("display.fonts.big")):
            big_size = self._parameters.get("display.fonts.big")
        elif (self._config.key_exists("display.fonts.big")):
            big_size = self._config.get("display.fonts.big")
        self._font_big = ImageFont.truetype(os.path.join(self._pic_dir, 'Font.ttc'), big_size)

        # Medium size
        if (self._parameters.key_exists("display.fonts.medium")):
            medium_size = self._parameters.get("display.fonts.medium")
        elif (self._config.key_exists("display.fonts.medium")):
            medium_size = self._config.get("display.fonts.medium")
        self._font_medium = ImageFont.truetype(os.path.join(self._pic_dir, 'Font.ttc'), medium_size)

        # Small size
        if (self._parameters.key_exists("display.fonts.small")):
            small_size = self._parameters.get("display.fonts.small")
        elif (self._config.key_exists("display.fonts.small")):
            small_size = self._config.get("display.fonts.small")
        self._font_small = ImageFont.truetype(os.path.join(self._pic_dir, 'Font.ttc'), small_size)
    
    
