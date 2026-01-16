from pyxavi import Config, Dictionary
from PIL import Image,ImageDraw,ImageFont
import os

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.objects.point import Point

from definitions import ROOT_DIR

class Canvas(PyXavi):

    _working_image: Image.Image = None
    _screen_size: Point = None

    DEFAULT_FONT_PATH = os.path.join(ROOT_DIR, "pitxu", "lib", "canvas", "fonts")
    FONT_FILE: str = os.path.join(DEFAULT_FONT_PATH, "Font_with_emojis.ttc")
    COLOR_MODE = "RGB"  # '1' for 1-bit images, 'L' for greyscale, 'RGB' for true color, 'RGBA' for true color with transparency

    FONT_TINY: ImageFont = None
    FONT_SMALL_EMOJI: ImageFont = None
    FONT_SMALL: ImageFont = None
    FONT_MEDIUM: ImageFont = None
    FONT_BIG: ImageFont = None
    FONT_HUGE: ImageFont = None
    FONT_ULTRA: ImageFont = None

    FONT_SIZE_TINY: int = None
    FONT_SIZE_SMALL_EMOJI: int = None
    FONT_SIZE_SMALL: int = None
    FONT_SIZE_MEDIUM: int = None
    FONT_SIZE_BIG: int = None
    FONT_SIZE_HUGE: int = None
    FONT_SIZE_ULTRA: int = None

    DEFAULT_FONT_SIZE_TINY = 16
    DEFAULT_FONT_SIZE_SMALL_EMOJI = 16
    DEFAULT_FONT_SIZE_SMALL = 20
    DEFAULT_FONT_SIZE_MEDIUM = 24
    DEFAULT_FONT_SIZE_BIG = 28
    DEFAULT_FONT_SIZE_HUGE = 45
    DEFAULT_FONT_SIZE_ULTRA = 85

    font_by_size: dict[str, ImageFont] = {}
    
    DEFAULT_STROKE: int = 1

    DEVICE_CONFIG_PREFIX = ""   # Example: "lcd" The separator "." will be added automatically

    @property
    def COLOR_BLACK(self) -> tuple | int:
        return 0 if self.COLOR_MODE == "1" else (0, 0, 0)
    
    @property
    def COLOR_WHITE(self) -> tuple | int:
        return 255 if self.COLOR_MODE == "1" else (255, 255, 255)
    
    @property
    def COLOR_RED(self) -> tuple | int:
        return 255 if self.COLOR_MODE == "1" else (255, 0, 0)
    
    @property
    def COLOR_GREEN(self) -> tuple | int:
        return 255 if self.COLOR_MODE == "1" else (0, 255, 0)
    
    @property
    def COLOR_BLUE(self) -> tuple | int:
        return 255 if self.COLOR_MODE == "1" else (0, 0, 255)

    @property
    def COLOR_YELLOW(self) -> tuple | int:
        return 255 if self.COLOR_MODE == "1" else (255, 255, 0)
    
    @property
    def COLOR_ORANGE(self) -> tuple | int:
        return 255 if self.COLOR_MODE == "1" else (255, 165, 0)

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Canvas, self).init_pyxavi(config=config, params=params)

        # If we receive a device config prefix in params, use it
        # This is useful to let the device to have its own config section
        if params.key_exists("device_config_prefix"):
            self.DEVICE_CONFIG_PREFIX = params.get("device_config_prefix")

        # Getting the screen size from params or config
        if params.key_exists("screen_size"):
            self._xlog.debug(f"Screen size provided in params: {params.get('screen_size').x}x{params.get('screen_size').y}")
            self._screen_size = params.get("screen_size")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".size")):
            self._xlog.debug(f"Screen size provided in config: " +
                             f"{self._xconfig.get(self.DEVICE_CONFIG_PREFIX + '.size.x')}" +
                             f"x{self._xconfig.get(self.DEVICE_CONFIG_PREFIX + '.size.y')}")
            self._screen_size = Point(
                self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".size.x"), 
                self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".size.y"))
        else:
            self._xlog.error("Screen size not provided in params nor config. Cannot continue.")
            raise Exception("Screen size not provided in params nor config. Cannot continue.")
        
        # Getting the font file from params or config or default
        if params.key_exists("font_file"):
            self.FONT_FILE = params.get("font_file")
        else:
            self.FONT_FILE = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.file", self.FONT_FILE)
        
        # Getting the image color mode from params or config or default
        if params.key_exists("color_mode"):
            self.COLOR_MODE = params.get("color_mode")
        else:
            self.COLOR_MODE = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".image.mode", self.COLOR_MODE)

        # Initialise fonts
        self._initialise_fonts()

        # Summary of the loaded configuration
        self._xlog.debug("Canvas loaded with the following configuration:")
        self._xlog.debug(f"  Device config prefix: {self.DEVICE_CONFIG_PREFIX}")
        self._xlog.debug(f"  Screen size: {self._screen_size.x}x{self._screen_size.y}")
        self._xlog.debug(f"  Font file: {self.FONT_FILE}")
        self._xlog.debug(f"  Color mode: {self.COLOR_MODE}")
        self._xlog.debug(f"  Font Tiny size: {self.FONT_SIZE_TINY}")
        self._xlog.debug(f"  Font Small size: {self.FONT_SIZE_SMALL}")
        self._xlog.debug(f"  Font Small Emoji size: {self.FONT_SIZE_SMALL_EMOJI}")
        self._xlog.debug(f"  Font Medium size: {self.FONT_SIZE_MEDIUM}")
        self._xlog.debug(f"  Font Big size: {self.FONT_SIZE_BIG}")
        self._xlog.debug(f"  Font Huge size: {self.FONT_SIZE_HUGE}")
        self._xlog.debug(f"  Font Ultra size: {self.FONT_SIZE_ULTRA}")

    def get_canvas(self, reset_base_image = True):
        if reset_base_image:
            self._reset_image()

        image = self.get_image(clear_background=True)
        return ImageDraw.Draw(image)
    
    def create_canvas_over_new_image(self) -> ImageDraw.ImageDraw:
        return self.get_canvas(reset_base_image=True)

    def close_canvas(self):
        self._reset_image()

    def get_screen_size(self) -> Point:
        return self._screen_size
    
    def get_image(self, clear_background: bool = True) -> Image.Image:
        """
        Returns the image that is being prepared to show

        If does not exists, creates it.
        """
        if self._working_image is None:

            # Default background color in a tuple as the default color mode is RGB
            background_color = self.COLOR_BLACK

            # In case the color mode is 1 we assume an eInk, and the background is either black or white
            if self.COLOR_MODE == "1" and clear_background:
                background_color = self.COLOR_WHITE

            self._working_image = Image.new(self.COLOR_MODE, (self._screen_size.x, self._screen_size.y), background_color)
            self._xlog.debug(f"Created new working image of size {self._working_image.size} and mode {self.COLOR_MODE}")

        return self._working_image
    
    def _reset_image(self):
        """
        The working image is a singleton. This resets it.
        """
        if self._working_image is not None:
            self._working_image = None
    
    def _initialise_fonts(self):
        """
        Initialise the fonts ULTRA, HUGE, BIG, MEDIUM and SMALL, TINY and SMALL_EMOJI.

        Priority is:
        - Params: in case we have runtime values
        - Config: to use the overall app setup
        - Class default: Fonts must exist, so this is the last resort

        Once initialised and prioritised, the font sizes are also stored in the respective FONT_SIZE_* attributes.
        """
        ultra_size = self.DEFAULT_FONT_SIZE_ULTRA
        huge_size = self.DEFAULT_FONT_SIZE_HUGE
        big_size = self.DEFAULT_FONT_SIZE_BIG
        medium_size = self.DEFAULT_FONT_SIZE_MEDIUM
        small_size = self.DEFAULT_FONT_SIZE_SMALL
        small_emoji_size = self.DEFAULT_FONT_SIZE_SMALL_EMOJI
        tiny_size = self.DEFAULT_FONT_SIZE_TINY

        self._xlog.debug(f"Initialising fonts from file: {self.FONT_FILE}")

        # Ultra size
        if (self._xparams.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.ultra")):
            ultra_size = self._xparams.get(self.DEVICE_CONFIG_PREFIX + ".fonts.ultra")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.ultra")):
            ultra_size = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.ultra")
        self.FONT_SIZE_ULTRA = ultra_size
        self.FONT_ULTRA = ImageFont.truetype(self.FONT_FILE, ultra_size)
        
        # Huge size
        if (self._xparams.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.huge")):
            huge_size = self._xparams.get(self.DEVICE_CONFIG_PREFIX + ".fonts.huge")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.huge")):
            huge_size = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.huge")
        self.FONT_SIZE_HUGE = huge_size
        self.FONT_HUGE = ImageFont.truetype(self.FONT_FILE, huge_size)

        # Big size
        if (self._xparams.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.big")):
            big_size = self._xparams.get(self.DEVICE_CONFIG_PREFIX + ".fonts.big")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.big")):
            big_size = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.big")
        self.FONT_SIZE_BIG = big_size
        self.FONT_BIG = ImageFont.truetype(self.FONT_FILE, big_size)

        # Medium size
        if (self._xparams.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.medium")):
            medium_size = self._xparams.get(self.DEVICE_CONFIG_PREFIX + ".fonts.medium")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.medium")):
            medium_size = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.medium")
        self.FONT_SIZE_MEDIUM = medium_size
        self.FONT_MEDIUM = ImageFont.truetype(self.FONT_FILE, medium_size)

        # Small size
        if (self._xparams.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.small")):
            small_size = self._xparams.get(self.DEVICE_CONFIG_PREFIX + ".fonts.small")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.small")):
            small_size = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.small")
        self.FONT_SIZE_SMALL = small_size
        self.FONT_SMALL = ImageFont.truetype(self.FONT_FILE, small_size)

        # Small emoji size
        if (self._xparams.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.small-emoji")):
            small_emoji_size = self._xparams.get(self.DEVICE_CONFIG_PREFIX + ".fonts.small-emoji")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.small-emoji")):
            small_emoji_size = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.small-emoji")
        self.FONT_SIZE_SMALL_EMOJI = small_emoji_size
        self.FONT_SMALL_EMOJI = ImageFont.truetype(self.FONT_FILE, small_emoji_size)

        # Tiny size
        if (self._xparams.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.tiny")):
            tiny_size = self._xparams.get(self.DEVICE_CONFIG_PREFIX + ".fonts.tiny")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.tiny")):
            tiny_size = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.tiny")
        self.FONT_SIZE_TINY = tiny_size
        self.FONT_TINY = ImageFont.truetype(self.FONT_FILE, tiny_size)

        # Prepare the font by size dictionary
        self.font_by_size = {
            f"{self.FONT_SIZE_TINY}": self.FONT_TINY,
            f"{self.FONT_SIZE_SMALL}": self.FONT_SMALL,
            f"{self.FONT_SIZE_SMALL_EMOJI}": self.FONT_SMALL_EMOJI,
            f"{self.FONT_SIZE_MEDIUM}": self.FONT_MEDIUM,
            f"{self.FONT_SIZE_BIG}": self.FONT_BIG,
            f"{self.FONT_SIZE_HUGE}": self.FONT_HUGE,
            f"{self.FONT_SIZE_ULTRA}": self.FONT_ULTRA
        }