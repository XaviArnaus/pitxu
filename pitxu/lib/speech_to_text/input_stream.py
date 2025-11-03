from pyxavi import Logger, Config, Dictionary, dd

import sounddevice
import logging

class InputStream:

    _config: Config = None
    _logger: logging = None
    _parameters: Dictionary = None

    samplerate=None,
    blocksize=None,
    device=None,
    channels=None,
    dtype=None,
    latency=None,
    extra_settings=None,
    callback=None,
    finished_callback=None,
    clip_off=None,
    dither_off=None,
    never_drop_input=None,
    prime_output_buffers_using_stream_callback=None

    _input_stream: sounddevice.RawInputStream = None

    def __init__(self, config: Config, params: Dictionary, samplerate=None, blocksize=None,
                 device=None, channels=None, dtype=None, latency=None,
                 extra_settings=None, callback=None, finished_callback=None,
                 clip_off=None, dither_off=None, never_drop_input=None,
                 prime_output_buffers_using_stream_callback=None):
        
        self._parameters = params
        self._config = config
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()

        self.samplerate=samplerate,
        self.blocksize=blocksize,
        self.device=device,
        self.channels=channels,
        self.dtype=dtype,
        self.latency=latency,
        self.extra_settings=extra_settings,
        self.callback=callback,
        self.finished_callback=finished_callback,
        self.clip_off=clip_off,
        self.dither_off=dither_off,
        self.never_drop_input=never_drop_input,
        self.prime_output_buffers_using_stream_callback=prime_output_buffers_using_stream_callback

        # self.initialize()
    
    # def initialize(self):
    #     if self._config.get("speech-to-text.mock", True):
    #         self._logger.info("Mocking Speech-to-Text by Config. Input Stream not initialized.")
    #     else:
    #         device_index = self._config.get("speech-to-text.input_device", None)
    #         self._logger.debug(f"Initializing Input Stream with device index: {device_index}")
    #         self._input_stream = sounddevice.RawInputStream(
    #             samplerate=self.samplerate,
    #             blocksize=self.blocksize,
    #             device=self.device,
    #             dtype=self.dtype,
    #             channels=self.channels,
    #             callback=self.callback)
    #         self._logger.debug("Done Initializing Input Stream")
    
    # def terminate(self):
    #     self._input_stream.close()
    
    def __enter__(self):
        """Start  the stream in the beginning of a "with" statement."""

        if self._config.get("speech-to-text.mock", True):
            self._logger.info("Mocking Speech-to-Text by Config. Microphone start is faked.")
        else:
            # self._input_stream.__enter__()
            # return self._input_stream
            self._input_stream = sounddevice.RawInputStream(
                samplerate=self.samplerate,
                blocksize=self.blocksize,
                device=self.device,
                dtype=self.dtype,
                channels=self.channels,
                callback=self.callback)
            return self._input_stream.__enter__()

    def __exit__(self, *args):
        """Stop and close the stream when exiting a "with" statement."""
        if self._config.get("speech-to-text.mock", True):
            self._logger.info("Mocking Speech-to-Text by Config. Microphone close is faked.")
        else:
            self._input_stream.__exit__()
    
    def start(self):
        self._logger.info("Mocking Speech-to-Text by Config. Microphone start() is faked.")
    
    def stop(self):
        self._logger.info("Mocking Speech-to-Text by Config. Microphone stop() is faked.")