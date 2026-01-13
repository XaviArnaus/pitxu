from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

class MockedOutputStream(PyXavi):

    def __init__(self, config: Config = None, dictionary: Dictionary = None):
        """Initialize the mocked raw input stream.

        Args:
            config (Config): The configuration object.
            dictionary (Dictionary): The dictionary object.
        """
        super(MockedOutputStream, self).init_pyxavi(config=config, dictionary=dictionary)
    
    def close(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def write(self, data):
        pass