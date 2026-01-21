from PIL import Image

class Device:

     def display(self, partial: bool = True):
         raise NotImplementedError("Command " + self.__class__.__name__ + " must implement display() method.")
    
     def clear(self):
         raise NotImplementedError("Command " + self.__class__.__name__ + " must implement clear() method.")