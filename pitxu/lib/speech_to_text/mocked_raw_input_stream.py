from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

# class MockedRawInputStream:

#     def __init__(self, samplerate=None, blocksize=None,
#                  device=None, channels=None, dtype=None, latency=None,
#                  extra_settings=None, callback=None, finished_callback=None,
#                  clip_off=None, dither_off=None, never_drop_input=None,
#                  prime_output_buffers_using_stream_callback=None):
#         pass

class MockedRawInputStream(PyXavi):

    def __init__(self, config: Config = None, dictionary: Dictionary = None):
        """Initialize the mocked raw input stream.

        Args:
            config (Config): The configuration object.
            dictionary (Dictionary): The dictionary object.
        """
        super(MockedRawInputStream, self).init_pyxavi(config=config, dictionary=dictionary)

    def __enter__(self):
        """Start  the stream in the beginning of a "with" statement."""
        # self.start()
        return self

    def __exit__(self, *args):
        """Stop and close the stream when exiting a "with" statement."""
        # self.stop()
        # self.close()
    
    def __call__(self):
        return self