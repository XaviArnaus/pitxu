import sounddevice

class WrapperRawInputStream(sounddevice.RawInputStream):
    
    def __call__(self):
        """Wrapper call method to create an instance of RawInputStream."""
        return self