import sounddevice

class MockedRawInputStream(sounddevice.RawInputStream):
    def __enter__(self):
        """Start  the stream in the beginning of a "with" statement."""
        # self.start()
        return self

    def __exit__(self, *args):
        """Stop and close the stream when exiting a "with" statement."""
        # self.stop()
        # self.close()