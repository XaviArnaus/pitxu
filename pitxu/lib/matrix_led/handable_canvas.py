from luma.core.render import canvas
from PIL import ImageDraw

class HandableCanvas(canvas):
    '''
    Extends luma.core.render.canvas to add handable features
    '''

    def get(self) -> ImageDraw.ImageDraw:
        return self.__enter__()

    def send_to_device(self):
        self.device.display(self.image)
    
    def close(self):
        self.__exit__(None, None, None)
