import sounddevice

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

class MockedRawInputStream(PyXavi):

    def __init__(self, config: Config, dictionary: Dictionary):
        """Initialize the mocked raw input stream.

        Args:
            config (Config): The configuration object.
            dictionary (Dictionary): The dictionary object.
        """
        super(MockedRawInputStream, self).__init__(config, dictionary)

    def __enter__(self):
        """Start  the stream in the beginning of a "with" statement."""
        # self.start()
        return self

    def __exit__(self, *args):
        """Stop and close the stream when exiting a "with" statement."""
        # self.stop()
        # self.close()