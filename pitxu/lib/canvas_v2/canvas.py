from pyxavi import Config, Dictionary
from PIL import Image,ImageDraw,ImageFont
import os

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.objects.point import Point

from definitions import ROOT_DIR

class Canvas(PyXavi):
    """
    Class that manages the canvas to draw on, including the working image and the fonts.
    """

    _working_image: Image.Image = None
    _screen_size: Point = None

    DEFAULT_FONT_PATH = os.path.join(ROOT_DIR, "pitxu", "fonts")
    FONT_FILE: str = os.path.join(DEFAULT_FONT_PATH, "Font_with_emojis.ttc")
    FONT_FILE_FOR_EMOJIS: str = os.path.join(DEFAULT_FONT_PATH, "NotoColorEmoji.ttf")
    COLOR_MODE = "RGBA"  # '1' for 1-bit images, 'L' for greyscale, 'RGB' for true color, 'RGBA' for true color with transparency

    FONT_TINY: ImageFont = None
    FONT_SMALL_EMOJI: ImageFont = None
    FONT_SMALL: ImageFont = None
    FONT_MEDIUM: ImageFont = None
    FONT_BIG: ImageFont = None
    FONT_HUGE: ImageFont = None
    FONT_ULTRA: ImageFont = None
    FONT_FIXED_EMOJI: ImageFont = None

    FONT_SIZE_TINY: int = None
    FONT_SIZE_SMALL_EMOJI: int = None
    FONT_SIZE_SMALL: int = None
    FONT_SIZE_MEDIUM: int = None
    FONT_SIZE_BIG: int = None
    FONT_SIZE_HUGE: int = None
    FONT_SIZE_ULTRA: int = None
    FONT_SIZE_FIXED_EMOJI: int = None

    DEFAULT_FONT_SIZE_TINY = 16
    DEFAULT_FONT_SIZE_SMALL_EMOJI = 16
    DEFAULT_FONT_SIZE_SMALL = 20
    DEFAULT_FONT_SIZE_MEDIUM = 24
    DEFAULT_FONT_SIZE_BIG = 28
    DEFAULT_FONT_SIZE_HUGE = 45
    DEFAULT_FONT_SIZE_ULTRA = 85
    DEFAULT_FONT_SIZE_FIXED_EMOJI = 109

    font_by_size: dict[str, ImageFont.ImageFont] = {}
    
    DEFAULT_STROKE: int = 1

    DEVICE_CONFIG_PREFIX = ""   # Example: "lcd" The separator "." will be added automatically

    COLOR_CODES = {
        "black": {
            "1": 0,
            "L": 0,
            "RGB": (0, 0, 0),
            "RGBA": (0, 0, 0, 255)
        },
        "white": {
            "1": 255,
            "L": 255,
            "RGB": (255, 255, 255),
            "RGBA": (255, 255, 255, 255)
        },
        "red": {
            "1": 255,
            "L": 0,
            "RGB": (255, 0, 0),
            "RGBA": (255, 0, 0, 255)
        },
        "green": {
            "1": 255,
            "L": 0,
            "RGB": (0, 255, 0),
            "RGBA": (0, 255, 0, 255)
        },
        "dark_green": {
            "1": 255,
            "L": 0,
            "RGB": (0, 128, 0),
            "RGBA": (0, 128, 0, 255)
        },
        "blue": {
            "1": 255,
            "L": 0,
            "RGB": (0, 0, 255),
            "RGBA": (0, 0, 255, 255)
        },
        "yellow": {
            "1": 255,
            "L": 0,
            "RGB": (255, 255, 0),
            "RGBA": (255, 255, 0, 255)
        },
        "dark_yellow": {
            "1": 255,
            "L": 0,
            "RGB": (128, 128, 0),
            "RGBA": (128, 128, 0, 255)
        },
        "orange": {
            "1": 255,
            "L": 0,
            "RGB": (255, 165, 0),
            "RGBA": (255, 165, 0, 255)
        }
    }

    VERBOSE_DEBUG: bool = False

    @property
    def COLOR_BLACK(self) -> tuple | int:
        return self.COLOR_CODES["black"][str(self.COLOR_MODE)]
    
    @property
    def COLOR_WHITE(self) -> tuple | int:
        return self.COLOR_CODES["white"][str(self.COLOR_MODE)]

    @property
    def COLOR_RED(self) -> tuple | int:
        return self.COLOR_CODES["red"][str(self.COLOR_MODE)]

    @property
    def COLOR_GREEN(self) -> tuple | int:
        return self.COLOR_CODES["green"][str(self.COLOR_MODE)]

    @property
    def COLOR_BLUE(self) -> tuple | int:
        return self.COLOR_CODES["blue"][str(self.COLOR_MODE)]

    @property
    def COLOR_YELLOW(self) -> tuple | int:
        return self.COLOR_CODES["yellow"][str(self.COLOR_MODE)]

    @property
    def COLOR_ORANGE(self) -> tuple | int:
        return self.COLOR_CODES["orange"][str(self.COLOR_MODE)]

    @property
    def COLOR_DARK_GREEN(self) -> tuple | int:
        return self.COLOR_CODES["dark_green"][str(self.COLOR_MODE)]

    @property
    def COLOR_DARK_YELLOW(self) -> tuple | int:
        return self.COLOR_CODES["dark_yellow"][str(self.COLOR_MODE)]

    @property
    def COLOR_FOREGROUND(self) -> tuple | int:
        return self.COLOR_BLACK if self.COLOR_MODE == "1" else self.COLOR_WHITE

    @property
    def COLOR_BACKGROUND(self) -> tuple | int:
        return self.COLOR_WHITE if self.COLOR_MODE == "1" else self.COLOR_BLACK

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Canvas, self).init_pyxavi(config=config, params=params)

        # If we receive a device config prefix in params, use it
        # This is useful to let the device to have its own config section
        if params.key_exists("device_config_prefix"):
            self.DEVICE_CONFIG_PREFIX = params.get("device_config_prefix")
        else:
            raise ValueError("'device_config_prefix' not provided in params. Cannot continue.")

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
        
        # Getting the font file from params
        if params.key_exists("font_file"):
            self._log_debug(f"Font file provided in params: {params.get('font_file')}")
            self.FONT_FILE = params.get("font_file")
        # In case the device has its own font file configured
        elif self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.file"):
            self._log_debug(f"Font file provided in config by the display: {self._xconfig.get(self.DEVICE_CONFIG_PREFIX + '.fonts.file')}")
            file_string = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.file")
            if "/" in file_string:
                self.FONT_FILE = file_string
            else:
                self.FONT_FILE = os.path.join(self.DEFAULT_FONT_PATH, file_string)
        # Lastly, the default from the application
        elif self._xconfig.key_exists("fonts.path") and self._xconfig.key_exists("fonts.default_filename"):
            self._log_debug(f"Font file provided in config by app default: {self._xconfig.get('fonts.path')}/{self._xconfig.get('fonts.default_filename')}")
            self.FONT_FILE = os.path.join(self._xconfig.get("fonts.path"), self._xconfig.get("fonts.default_filename", "Font_with_emojis.ttc"))

        else:
            self._log_debug(f"Font file set to class default: {self.FONT_FILE}")
        
        # The emoji fnt file for the colored emojis has only a fixed size, intended to be added into a PIL image and the you can play.
        self.FONT_FILE_FOR_EMOJIS = os.path.join(
            self._xconfig.get("fonts.path", self.DEFAULT_FONT_PATH),
            self._xconfig.get("fonts.fixed_emojis_only_filename"), 
            self.FONT_FILE_FOR_EMOJIS)
        
        # Getting the image color mode from params or config or default
        if params.key_exists("color_mode"):
            self.COLOR_MODE = str(params.get("color_mode"))
        else:
            self.COLOR_MODE = str(self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".image.mode", self.COLOR_MODE))

        # Initialise fonts
        self._initialise_fonts()

        # Summary of the loaded configuration
        self.log_summary("Canvas Initialization", [
            ("Device config prefix", self.DEVICE_CONFIG_PREFIX),
            ("Screen size", f"{self._screen_size.x}x{self._screen_size.y}"),
            ("Font file", self.FONT_FILE),
            ("Color mode", self.COLOR_MODE),
            ("Font Tiny size", self.FONT_SIZE_TINY),
            ("Font Small size", self.FONT_SIZE_SMALL),
            ("Font Small Emoji size", self.FONT_SIZE_SMALL_EMOJI),
            ("Font Medium size", self.FONT_SIZE_MEDIUM),
            ("Font Big size", self.FONT_SIZE_BIG),
            ("Font Huge size", self.FONT_SIZE_HUGE),
            ("Font Ultra size", self.FONT_SIZE_ULTRA),
            ("Font Fixed Emoji size", self.FONT_SIZE_FIXED_EMOJI),

        ])

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
    
    def get_image(self, clear_background: bool = True, size: Point = None) -> Image.Image:
        """
        Returns the image that is being prepared to show

        If does not exists, creates it.
        """
        if self._working_image is None:

            self._working_image = self.create_new_image(clear_background=clear_background, size=size)
            self._log_debug("Created new working image for canvas.")

        return self._working_image
    
    def create_new_image(self, clear_background: bool = True, size: Point = None) -> Image.Image:
        """
        Creates and returns a new image to draw on, without modifying the working image.

        This is useful for the macros that want to draw on a separate image and then combine it with the working image.
        """
        # Default background color in a tuple as the default color mode is RGB
        background_color = self.COLOR_BLACK

        # In case the color mode is 1 we assume an eInk, and the background is either black or white
        if self.COLOR_MODE == "1" and clear_background:
            background_color = self.COLOR_WHITE

        if size is None:
            size = self._screen_size

        new_image = Image.new(str(self.COLOR_MODE), (size.x, size.y), background_color)
        self._log_debug(f"Created new image of size {new_image.size} and mode {self.COLOR_MODE}")

        return new_image

    def combine_into_image(self, overlay_image: Image.Image, position: Point = Point(0,0), use_alpha_composite: bool = True):
        """
        Combines the given overlay image onto the working image at the given position.
        """
        base_image = self.get_image(clear_background=False)
        if use_alpha_composite:
            base_image.alpha_composite(overlay_image, dest=(position.x, position.y))
        else:
            base_image.paste(overlay_image, (position.x, position.y))
        self._log_debug(f"Combined ({'alpha_composite' if use_alpha_composite else 'paste'}) overlay image of size {overlay_image.size} at position ({position.x}, {position.y}) onto working image.")

    def get_font_by_size(self, size: int) -> ImageFont:
        """
        Returns the font object for the given size.

        If the size does not exist, returns the medium font.
        """
        if f"{size}" in self.font_by_size:
            return self.font_by_size[f"{size}"]
        else:
            self._xlog.warning(f"Font size {size} not found. Returning medium font size {self.FONT_SIZE_MEDIUM}.")
            return self.FONT_MEDIUM
    
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
        fixed_emoji_size = self.DEFAULT_FONT_SIZE_FIXED_EMOJI

        engine = 0
        mode = "L"

        self._xlog.debug(f"Initialising fonts from file: {self.FONT_FILE}")

        # Fixed emoji size
        if (self._xparams.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.fixed_emoji")):
            fixed_emoji_size = self._xparams.get(self.DEVICE_CONFIG_PREFIX + ".fonts.fixed_emoji")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.fixed_emoji")):
            fixed_emoji_size = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.fixed_emoji")
        self.FONT_SIZE_FIXED_EMOJI = fixed_emoji_size
        self.FONT_FIXED_EMOJI = ImageFont.truetype(self.FONT_FILE, fixed_emoji_size, layout_engine=engine)

        # Ultra size
        if (self._xparams.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.ultra")):
            ultra_size = self._xparams.get(self.DEVICE_CONFIG_PREFIX + ".fonts.ultra")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.ultra")):
            ultra_size = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.ultra")
        self.FONT_SIZE_ULTRA = ultra_size
        self.FONT_ULTRA = ImageFont.truetype(self.FONT_FILE, ultra_size, layout_engine=engine)
        
        # Huge size
        if (self._xparams.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.huge")):
            huge_size = self._xparams.get(self.DEVICE_CONFIG_PREFIX + ".fonts.huge")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.huge")):
            huge_size = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.huge")
        self.FONT_SIZE_HUGE = huge_size
        self.FONT_HUGE = ImageFont.truetype(self.FONT_FILE, huge_size, layout_engine=engine)

        # Big size
        if (self._xparams.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.big")):
            big_size = self._xparams.get(self.DEVICE_CONFIG_PREFIX + ".fonts.big")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.big")):
            big_size = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.big")
        self.FONT_SIZE_BIG = big_size
        self.FONT_BIG = ImageFont.truetype(self.FONT_FILE, big_size, layout_engine=engine)

        # Medium size
        if (self._xparams.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.medium")):
            medium_size = self._xparams.get(self.DEVICE_CONFIG_PREFIX + ".fonts.medium")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.medium")):
            medium_size = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.medium")
        self.FONT_SIZE_MEDIUM = medium_size
        self.FONT_MEDIUM = ImageFont.truetype(self.FONT_FILE, medium_size, layout_engine=engine)

        # Small size
        if (self._xparams.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.small")):
            small_size = self._xparams.get(self.DEVICE_CONFIG_PREFIX + ".fonts.small")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.small")):
            small_size = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.small")
        self.FONT_SIZE_SMALL = small_size
        self.FONT_SMALL = ImageFont.truetype(self.FONT_FILE, small_size, layout_engine=engine)

        # Small emoji size
        if (self._xparams.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.small-emoji")):
            small_emoji_size = self._xparams.get(self.DEVICE_CONFIG_PREFIX + ".fonts.small-emoji")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.small-emoji")):
            small_emoji_size = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.small-emoji")
        self.FONT_SIZE_SMALL_EMOJI = small_emoji_size
        self.FONT_SMALL_EMOJI = ImageFont.truetype(self.FONT_FILE, small_emoji_size, layout_engine=engine)

        # Tiny size
        if (self._xparams.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.tiny")):
            tiny_size = self._xparams.get(self.DEVICE_CONFIG_PREFIX + ".fonts.tiny")
        elif (self._xconfig.key_exists(self.DEVICE_CONFIG_PREFIX + ".fonts.tiny")):
            tiny_size = self._xconfig.get(self.DEVICE_CONFIG_PREFIX + ".fonts.tiny")
        self.FONT_SIZE_TINY = tiny_size
        self.FONT_TINY = ImageFont.truetype(self.FONT_FILE, tiny_size, layout_engine=engine)

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