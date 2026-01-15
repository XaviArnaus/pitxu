from PIL import Image

class Device:

    def display(self, image: Image.Image, partial: bool = True):
         raise NotImplementedError("Command " + self.__class__.__name__ + " must implement display() method.")
    
    def clear(self):
         raise NotImplementedError("Command " + self.__class__.__name__ + " must implement clear() method.")