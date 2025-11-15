import sys
import os
import logging
import time

from PIL import Image,ImageDraw,ImageFont

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary

from ..objects.point import Point

class EinkDisplay:

    _epd = None
    _xparams: Dictionary = None
    _xconfig: Config = None
    _xlog: logging = None
    _pic_dir: str = None
    _working_image: Image.Image = None
    _screen_size: Point = None

    FONT_SMALL: ImageFont = None
    FONT_MEDIUM: ImageFont = None
    FONT_BIG: ImageFont = None

    DEFAULT_FONT_BIG_SIZE = 22
    DEFAULT_FONT_MEDIUM_SIZE = 14
    DEFAULT_FONT_SMALL_SIZE = 10

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_MOCKED_IMAGES_PATH = "mocked/eink/"

    def __init__(self, config: Config, params: Dictionary):

        # Possible runtime parameters
        self._xparams = params

        # Config is mandatory
        if config is None:
            raise RuntimeError("Config can not be None")
        self._xconfig = config

        # Common Logger
        self._xlog = Logger(config=config, base_path=self._xparams.get("base_path", "")).get_logger()
        
        # Initialise the display
        self._initialise_display()

        # Initialise fonts
        self._initialise_fonts()
    
    def create_canvas(self, reset_base_image = True):
        if reset_base_image:
            self._reset_image()

        image = self._get_image(True)
        return ImageDraw.Draw(image)
    
    def display(self, partial: bool = True):
        if (not self._is_gpio_allowed()):
            file_path = self._xconfig.get("storage.path", self.DEFAULT_STORAGE_PATH) + self.DEFAULT_MOCKED_IMAGES_PATH + time.strftime("%Y%m%d-%H%M%S") + ".png"
            self._working_image.save(file_path)
            file_path = self._xconfig.get("storage.path", self.DEFAULT_STORAGE_PATH) + self.DEFAULT_MOCKED_IMAGES_PATH + "_latest.png"
            self._working_image.save(file_path)
        else:
            if self._xconfig.get("display.rotate", False):
                self._working_image = self._working_image.rotate(180)
            
            # The example uses display_fast(). Tests show that display() works. Now testing display_fast().
            # self._epd.display(self._epd.getbuffer(self._working_image))
            # self._epd.display_fast(self._epd.getbuffer(self._working_image))
            if partial:
                self._epd.displayPartial(self._epd.getbuffer(self._working_image))
            else:
                self._epd.display_fast(self._epd.getbuffer(self._working_image))
    
    def clear(self):
        if (self._is_gpio_allowed()):
            self._epd.Clear(0xFF)
            self._xlog.debug("eInk cleared")
        else:
            self._xlog.warning("Did not clear the display. GPIO interaction not allowed.")
        # Needed to clean up the canvas.
        self._reset_image()
    
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
        draw.text((120, 60), 'e-Paper demo', font = self.FONT_SMALL, fill = 0)
        draw.text((110, 90), u'微雪电子', font = self.FONT_BIG, fill = 0)
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
            # # Apparently, the e-ink display is rotated 90 degrees, so swap coordinates for real GPIO work.
            if (self._is_gpio_allowed()): 
                self._working_image = Image.new('1', (self._screen_size.y, self._screen_size.x), 255 if clear_background else 0)
            else:    
                self._working_image = Image.new('1', (self._screen_size.x, self._screen_size.y), 255 if clear_background else 0)
        return self._working_image

    def _reset_image(self):
        """
        The working image is a singleton. This resets it.
        """
        if self._working_image is not None:
            self._working_image = None
    
    def _is_gpio_allowed(self):
        import platform

        os = platform.system()        
        if (os.lower() != "linux"):
            self._xlog.warning("OS is not Linux, auto mocking eInk")
            return False
        if (self._xconfig.get("display.mock", True)):
            self._xlog.warning("Mocking eInk by Config")
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
        self._pic_dir = os.path.join(self._xparams.get("base_path", ""), 'pitxu', 'pic')
        libdir = os.path.join(self._xparams.get("base_path", ""), 'pitxu', 'lib')

        # Don't initialise if not allowed
        if (not self._is_gpio_allowed()):
            # Setup base data
            self._screen_size = Point(self._xconfig.get("display.size.x"), self._xconfig.get("display.size.y"))
            self._xlog.warning("GPIO is not allowed, avoiding initializing eInk")
            return

        # Lib should be in the sys path
        self._xlog.debug("Trying to load the lib directory at: " + libdir)
        if os.path.exists(libdir):
            sys.path.append(libdir)
        else:
            self._xlog.warning("Could not find the lib directory at: " + libdir)
            print("lib does not exists")
        from waveshare_epd.epd2in13_V4 import EPD

        # Initialise the display controller
        self._xlog.debug("Initialising eInk controller")
        self._epd = EPD()

        # Initialise the display itself
        self._xlog.debug("Initialising eInk display")
        self._epd.init()
        if self._xconfig.get("display.initial_clear"):
            self._xlog.debug("Cleaning for the first time")
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
        if (self._xparams.key_exists("display.fonts.big")):
            big_size = self._xparams.get("display.fonts.big")
        elif (self._xconfig.key_exists("display.fonts.big")):
            big_size = self._xconfig.get("display.fonts.big")
        self.FONT_BIG = ImageFont.truetype(os.path.join(self._pic_dir, 'Font.ttc'), big_size)

        # Medium size
        if (self._xparams.key_exists("display.fonts.medium")):
            medium_size = self._xparams.get("display.fonts.medium")
        elif (self._xconfig.key_exists("display.fonts.medium")):
            medium_size = self._xconfig.get("display.fonts.medium")
        self.FONT_MEDIUM = ImageFont.truetype(os.path.join(self._pic_dir, 'Font.ttc'), medium_size)

        # Small size
        if (self._xparams.key_exists("display.fonts.small")):
            small_size = self._xparams.get("display.fonts.small")
        elif (self._xconfig.key_exists("display.fonts.small")):
            small_size = self._xconfig.get("display.fonts.small")
        self.FONT_SMALL = ImageFont.truetype(os.path.join(self._pic_dir, 'Font.ttc'), small_size)
    
    def close(self):
        if self._epd is not None:
            self._epd.sleep()
    
