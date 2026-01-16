import os
from pyxavi import Config, Dictionary
from datetime import datetime
from PIL import Image

from pitxu.lib.abstract.pyxavi import PyXavi

class MockedST7789(PyXavi):

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_MOCKED_IMAGES_PATH = "mocked/lcd/"

    width: int = 320
    height: int = 240

    path_for_mocked_images: str = DEFAULT_STORAGE_PATH + DEFAULT_MOCKED_IMAGES_PATH

    def __init__(self, config: Config = None, params: Dictionary = None, *args, **kwargs):
        super(MockedST7789, self).init_pyxavi(config=config, params=params)

        if params is not None:
            if params.key_exists("width"):
                self.width = int(params.get("width"))
            if params.key_exists("height"):
                self.height = int(params.get("height"))

        self.path_for_mocked_images = self._xconfig.get("storage.path", self.DEFAULT_STORAGE_PATH) + self.DEFAULT_MOCKED_IMAGES_PATH
        if os.path.exists(self.path_for_mocked_images) == False:
            os.makedirs(self.path_for_mocked_images)

    def Init(self):
        pass

    def clear(self, image):
        pass

    def bl_DutyCycle(self, duty):
        pass

    def ShowImage(self, image: Image.Image,Xstart=0,Ystart=0):
        image = image.rotate(180)
        file_path = self.path_for_mocked_images + datetime.now().strftime("%Y%m%d-%H%M%S.%f") + ".png"
        image.save(file_path)
        file_path = self.path_for_mocked_images + "_latest.png"
        image.save(file_path)

    def module_exit(self):
        pass