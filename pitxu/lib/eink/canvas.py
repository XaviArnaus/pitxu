from pyxavi import Config, Dictionary
from PIL import Image,ImageDraw,ImageFont
import logging, os, time, sys

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.objects import Point


class EinkCanvas(PyXavi):

    _pic_dir: str = None
    _working_image: Image.Image = None
    _screen_size: Point = None

    # FONT_FILE: str = "pitxu/pic/Font.ttc"
    FONT_FILE: str = "pitxu/pic/Font_with_emojis.ttc"

    FONT_SMALL: ImageFont = None
    FONT_MEDIUM: ImageFont = None
    FONT_BIG: ImageFont = None
    FONT_HUGE: ImageFont = None

    FONT_BIG_SIZE = 22
    FONT_MEDIUM_SIZE = 14
    FONT_SMALL_SIZE = 10
    FONT_HUGE_SIZE = 45

    DEFAULT_STROKE: int = 1
    COLOR_BLACK: int = 0
    COLOR_WHITE: int = 1

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_MOCKED_IMAGES_PATH = "mocked/eink/"

    def __init__(self, config: Config = None, params: Dictionary = None, screen_size: Point = None):
        super(EinkCanvas, self).init_pyxavi(config=config, params=params)

        # Set the screen size given.
        if screen_size is not None:
            self._screen_size = screen_size
        else:
            if self._is_gpio_allowed():
                self._screen_size = Point(self._xconfig.get("display.size.x"), self._xconfig.get("display.size.x"))
            else:
                self._screen_size = Point(self._xconfig.get("display.size.x"), self._xconfig.get("display.size.y"))

        # Initialise fonts
        self._initialise_fonts()

    def create_canvas(self, reset_base_image = True):
        if reset_base_image:
            self._reset_image()

        image = self.get_image(clear_background=True)
        return ImageDraw.Draw(image)
    
    def create_canvas_over_new_image(self):
        self._reset_image()
        image = self.get_image(clear_background=True)
        return ImageDraw.Draw(image)

    def get_screen_size(self) -> Point:
        return self._screen_size
    
    def get_image(self, clear_background: bool = True) -> Image.Image:
        """
        Returns the image that is being prepared to show

        If does not exists, creates it.
        """
        if self._working_image is None:
            self._working_image = Image.new('1', (self._screen_size.x, self._screen_size.y), 255 if clear_background else 0)
            # # Apparently, the e-ink display is rotated 90 degrees, so swap coordinates for real GPIO work.
            # if (self._is_gpio_allowed()):
            #     self._working_image = Image.new('1', (self._screen_size.y, self._screen_size.x), 255 if clear_background else 0)
            # else:
            #     self._working_image = Image.new('1', (self._screen_size.x, self._screen_size.y), 255 if clear_background else 0)
            if (self._is_gpio_allowed()):
                self._working_image = self._working_image.rotate(-90, expand=True)
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
    
    def _initialise_fonts(self):
        """
        Initialise the fonts BIG, MEDIUM and SMALL.
        Priority is:
        - Params: in case we have runtime values
        - Config: to use the overall app setup
        - Class default: Fonts must exist, so this is the last resort
        """
        big_size = self.FONT_BIG_SIZE
        medium_size = self.FONT_MEDIUM_SIZE
        small_size = self.FONT_SMALL_SIZE
        huge_size = self.FONT_HUGE_SIZE

        # Huge size
        if (self._xparams.key_exists("display.fonts.huge")):
            huge_size = self._xparams.get("display.fonts.huge")
        elif (self._xconfig.key_exists("display.fonts.huge")):
            huge_size = self._xconfig.get("display.fonts.huge")
        self.FONT_HUGE = ImageFont.truetype(self.FONT_FILE, huge_size)

        # Big size
        if (self._xparams.key_exists("display.fonts.big")):
            big_size = self._xparams.get("display.fonts.big")
        elif (self._xconfig.key_exists("display.fonts.big")):
            big_size = self._xconfig.get("display.fonts.big")
        self.FONT_BIG = ImageFont.truetype(self.FONT_FILE, big_size)

        # Medium size
        if (self._xparams.key_exists("display.fonts.medium")):
            medium_size = self._xparams.get("display.fonts.medium")
        elif (self._xconfig.key_exists("display.fonts.medium")):
            medium_size = self._xconfig.get("display.fonts.medium")
        self.FONT_MEDIUM = ImageFont.truetype(self.FONT_FILE, medium_size)

        # Small size
        if (self._xparams.key_exists("display.fonts.small")):
            small_size = self._xparams.get("display.fonts.small")
        elif (self._xconfig.key_exists("display.fonts.small")):
            small_size = self._xconfig.get("display.fonts.small")
        self.FONT_SMALL = ImageFont.truetype(self.FONT_FILE, small_size)
    
    # def test(self):
    #     logging.info("Drawing on the image...")
    #     draw = self.create_canvas()
    #     draw.rectangle([(0,0),(50,50)],outline = 0)
    #     draw.rectangle([(55,0),(100,50)],fill = 0)
    #     draw.line([(0,0),(50,50)], fill = 0,width = 1)
    #     draw.line([(0,50),(50,0)], fill = 0,width = 1)
    #     draw.chord((10, 60, 50, 100), 0, 360, fill = 0)
    #     draw.ellipse((55, 60, 95, 100), outline = 0)
    #     draw.pieslice((55, 60, 95, 100), 90, 180, outline = 0)
    #     draw.pieslice((55, 60, 95, 100), 270, 360, fill = 0)
    #     draw.polygon([(110,0),(110,50),(150,25)],outline = 0)
    #     draw.polygon([(190,0),(190,50),(150,25)],fill = 0)
    #     draw.text((120, 60), 'e-Paper demo', font = self.FONT_SMALL, fill = 0)
    #     draw.text((110, 90), u'微雪电子', font = self.FONT_BIG, fill = 0)
    #     # image = image.rotate(180) # rotate
    #     self.display()
    #     time.sleep(2)
    #     self.clear()
    #     time.sleep(2)