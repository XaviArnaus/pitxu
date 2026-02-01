from PIL import Image, ImageDraw

from pyxavi import Config, Logger, Dictionary

from datetime import datetime
import logging, os


class EmulatedCanvas(object):
    """
    A canvas returns a properly-sized :py:mod:`PIL.ImageDraw` object onto
    which the caller can draw upon. As soon as the with-block completes, the
    resultant image is flushed onto the device.

    This is an emulation to mimic `luma.core.render.canvas`
    """

    _xparams: Dictionary = None
    _xconfig: Config = None
    _xlog: logging = None

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_MOCKED_IMAGES_PATH = "mocked/matrix/"

    path_for_mocked_images: str = None

    MULTIPLIER_FACTOR = 10   # To have a bigger image for better visualization

    def __init__(self, config: Config, params: Dictionary, mode: str, size: tuple):
        self._xconfig = config
        self._xparams = params
        self._xlog = Logger(config=config, base_path=self._xparams.get("base_path", "")).get_logger()

        self.draw = None
        self.image = Image.new(mode, size)

        self.path_for_mocked_images = self._xconfig.get("storage.path", self.DEFAULT_STORAGE_PATH) + self.DEFAULT_MOCKED_IMAGES_PATH
        if os.path.exists(self.path_for_mocked_images) == False:
            os.makedirs(self.path_for_mocked_images)

    def __enter__(self) -> ImageDraw:
        self.draw = ImageDraw.Draw(self.image)
        return self.draw

    def __exit__(self, type, value, traceback):
        if type is None:

            self._save_image()

        del self.draw   # Tidy up the resources
        return False    # Never suppress exceptions
    
    def _save_image(self):
        # Save the image
        if not self._xconfig.get("matrix_led.discard_mocked_images", False):
            image = self.image.resize((self.image.width * self.MULTIPLIER_FACTOR, self.image.height * self.MULTIPLIER_FACTOR), Image.Resampling.NEAREST)
            file_path = self.path_for_mocked_images + datetime.now().strftime("%Y%m%d-%H%M%S.%f") + ".png"
            image.save(file_path)
            file_path = self.path_for_mocked_images + "_latest.png"
            image.save(file_path)

class HandableEmulatedCanvas(EmulatedCanvas):
    '''
    Extends luma.core.render.canvas to add handable features
    '''
    def get(self) -> ImageDraw.ImageDraw:
        return self.__enter__()

    def send_to_device(self):
        self._save_image()

    def close(self):
        return False