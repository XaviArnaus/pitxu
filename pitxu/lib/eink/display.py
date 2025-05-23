import sys
import os
import logging
import traceback
import time

# Lib should be in the sys path
picdir = os.path.join("..", "..", os.path.dirname(os.path.realpath(__file__)), 'pic')
libdir = os.path.join("..", "..", os.path.dirname(os.path.realpath(__file__)), 'lib')
if os.path.exists(libdir):
    sys.path.append(libdir)
else:
    print("lib does not exists")

from ..waveshare_epd import epd2in13_V4
from PIL import Image,ImageDraw,ImageFont

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary

class EinkDisplay:

    _epd = None
    _parameters: Dictionary = None
    _config: Config = None
    _logger: logging = None
    _font_big = None
    _font_medium = None
    _font_small = None

    DEFAULT_FONT_BIG_SIZE = 24
    DEFAULT_FONT_MEDIUM_SIZE = 20
    DEFAULT_FONT_SMALL_SIZE = 15

    def __init__(self, config: Config = None, params: dict = {}):

        # Possible runtime parameters
        self._parameters = Dictionary(params)

        # Config is mandatory
        if config is None:
            raise RuntimeError("Config can not be None")
        self._config = config

        # Common Logger
        self._logger = Logger(config=config, base_path=params.get("base_path", "")).get_logger()
        
        # Initialise the display controller
        self._epd = epd2in13_V4.EPD()

        # Initialise the display itself
        self._epd.init()
        self._epd.Clear(0xFF)

        # Initialise fonts
        self._initialise_fonts()
    
    def test(self):
        logging.info("E-paper refresh")
        self._epd.init()
        logging.info("1.Drawing on the image...")
        image = Image.new('1', (self._epd.height, self._epd.width), 255)  # 255: clear the frame    
        draw = ImageDraw.Draw(image)
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
        self._epd.display(self._epd.getbuffer(image))
        time.sleep(2)
    
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
        self._font_big = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), big_size)

        # Medium size
        if (self._parameters.key_exists("display.fonts.medium")):
            medium_size = self._parameters.get("display.fonts.medium")
        elif (self._config.key_exists("display.fonts.medium")):
            medium_size = self._config.get("display.fonts.medium")
        self._font_medium = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), medium_size)

        # Small size
        if (self._parameters.key_exists("display.fonts.small")):
            small_size = self._parameters.get("display.fonts.small")
        elif (self._config.key_exists("display.fonts.small")):
            small_size = self._config.get("display.fonts.small")
        self._font_small = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), small_size)
    
    
