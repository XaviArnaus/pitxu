from PIL import Image, ImageDraw

from pyxavi import Config, Logger, Dictionary

import time
import logging


class EmulatedCanvas(object):
    """
    A canvas returns a properly-sized :py:mod:`PIL.ImageDraw` object onto
    which the caller can draw upon. As soon as the with-block completes, the
    resultant image is flushed onto the device.

    This is an emulation to mimic `luma.core.render.canvas`
    """

    _parameters: Dictionary = None
    _config: Config = None
    _logger: logging = None

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_MOCKED_IMAGES_PATH = "mocked/matrix/"

    def __init__(self, config: Config, mode: str, size: tuple):
        self.draw = None
        self.image = Image.new(mode, size)

    def __enter__(self) -> ImageDraw:
        self.draw = ImageDraw.Draw(self.image)
        return self.draw

    def __exit__(self, type, value, traceback):
        if type is None:
            # Save the image
            file_path = self._config.get("storage.path", self.DEFAULT_STORAGE_PATH) + self.DEFAULT_MOCKED_IMAGES_PATH + time.strftime("%Y%m%d-%H%M%S") + ".png"
            self.image.save(file_path)
            file_path = self._config.get("storage.path", self.DEFAULT_STORAGE_PATH) + self.DEFAULT_MOCKED_IMAGES_PATH + "_latest.png"
            self.image.save(file_path)

        del self.draw   # Tidy up the resources
        return False    # Never suppress exceptions