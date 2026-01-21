import sys
import os
from datetime import datetime

from PIL import Image, ImageFont

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.canvas.canvas import Canvas
from pitxu.lib.objects import Point

class EinkDisplay(PyXavi):

    _epd = None
    _pic_dir: str = None
    _screen_size: Point = None
    # _canvas: EinkCanvas = None
    _canvas: Canvas = None

    font_by_size = {}

    FONT_SMALL: ImageFont = None
    FONT_MEDIUM: ImageFont = None
    FONT_BIG: ImageFont = None
    FONT_HUGE: ImageFont = None

    COLOR_BLACK: int = None
    COLOR_WHITE: int = None

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_MOCKED_IMAGES_PATH = "mocked/eink/"

    def __init__(self, config: Config, params: Dictionary):
        super(EinkDisplay, self).init_pyxavi(config=config, params=params)
        
        # Initialise the display
        self._initialise_display()

        # Initialise the Canvas
        # self._canvas = EinkCanvas(screen_size=self._screen_size, config=self._xconfig, params=self._xparams)
        self._canvas = Canvas(config=self._xconfig, params=self._xparams)

        # Before migrating all the code, shortcut it here
        self.FONT_SMALL = self._canvas.FONT_SMALL
        self.FONT_MEDIUM = self._canvas.FONT_MEDIUM
        self.FONT_BIG = self._canvas.FONT_BIG
        self.FONT_HUGE = self._canvas.FONT_HUGE
        self.COLOR_BLACK = self._canvas.COLOR_BLACK
        self.COLOR_WHITE = self._canvas.COLOR_WHITE

        self.font_by_size = {
            f"{Canvas.FONT_SIZE_SMALL}": self._canvas.FONT_SMALL,
            f"{Canvas.FONT_SIZE_MEDIUM}": self._canvas.FONT_MEDIUM,
            f"{Canvas.FONT_SIZE_BIG}": self._canvas.FONT_BIG,
            f"{Canvas.FONT_SIZE_HUGE}": self._canvas.FONT_HUGE
        }

        self.path_for_mocked_images = self._xconfig.get("storage.path", self.DEFAULT_STORAGE_PATH) + self.DEFAULT_MOCKED_IMAGES_PATH
        if os.path.exists(self.path_for_mocked_images) == False:
            os.makedirs(self.path_for_mocked_images)
    
    def get_font_by_size(self, size: int) -> ImageFont:
        return self.font_by_size[f"{size}"]

    def create_canvas(self, reset_base_image = True):
        # return self._canvas.create_canvas(reset_base_image=reset_base_image)
        return self._canvas.get_canvas(reset_base_image=reset_base_image)
    
    def get_image(self, clear_background: bool = True) -> Image.Image:
        return self._canvas.get_image(clear_background=clear_background)
    
    # def display(self, partial: bool = True):
    #     """
    #     Displays the current working image on the eInk display.

    #     Args:
    #         partial: Whether to use partial update or full update.
    #     """
    #     self.display_arbitrary_image(self._canvas.get_image(), partial=partial)
    
    def display(self, image: Image.Image, partial: bool = True):
        """
        Displays an arbitrary image on the eInk display.

        Args:
            image: The image to display. Must be in mode '1' (1-bit pixels, black and white).
            partial: Whether to use partial update or full update.
        """
        if (not self._is_gpio_allowed()):
            file_path = self.path_for_mocked_images + datetime.now().strftime("%Y%m%d-%H%M%S.%f") + ".png"
            image.save(file_path)
            file_path = self.path_for_mocked_images + "_latest.png"
            image.save(file_path)
        else:
            self.flush_to_device(image, partial=partial)
    
    def flush_to_device(self, image: Image.Image, partial: bool = True):
        if self._xconfig.get("eink.rotate", False):
                image = image.rotate(180)
        if partial:
            self._epd.displayPartial(self._epd.getbuffer(image))
        else:
            self._epd.display_fast(self._epd.getbuffer(image))

    def clear(self):
        if (self._is_gpio_allowed()):
            self._epd.Clear(0xFF)
            self._xlog.debug("eInk cleared")
        else:
            self._xlog.warning("Did not clear the display. GPIO interaction not allowed.")
        # Needed to clean up the canvas.
        self._canvas._reset_image()
    
    def get_screen_size(self) -> Point:
        """
        Returns the screen size as a Point (width, height)
        """
        return self._screen_size
    
    def _is_gpio_allowed(self):
        import platform

        os = platform.system()        
        if (os.lower() != "linux"):
            self._xlog.debug("OS is not Linux, auto mocking eInk")
            return False
        if (self._xconfig.get("eink.mock", True)):
            self._xlog.debug("Mocking eInk by Config")
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
            self._screen_size = Point(self._xconfig.get("eink.size.x"), self._xconfig.get("eink.size.y"))
            self._xlog.warning("GPIO is not allowed, avoiding initializing eInk")
        else:
            # Lib should be in the sys path
            self._xlog.debug("Trying to load the lib directory at: " + libdir)
            if os.path.exists(libdir):
                sys.path.append(libdir)
            else:
                self._xlog.warning("Could not find the lib directory at: " + libdir)
                print("lib does not exists")
            from .waveshare_epd.epd2in13_V4 import EPD

            # Initialise the display controller
            self._xlog.debug("Initialising eInk controller")
            self._epd = EPD()

            # Initialise the display itself
            self._xlog.debug("Initialising eInk display")
            self._epd.init()
            if self._xconfig.get("eink.initial_clear"):
                self._xlog.debug("Cleaning for the first time")
                self._epd.Clear(0xFF)

            # Setup base data
            self._screen_size = Point(self._epd.width, self._epd.height)

    def close(self):
        if self._epd is not None:
            self._epd.sleep()
    
