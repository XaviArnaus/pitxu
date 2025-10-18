import numpy as np

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary

import logging

class PiperMultiprocess:

    MODELS_PATH = "tts_models/"

    _config: Config = None
    _logger: logging = None
    _parameters: Dictionary = None

    _model: None
    _voice: None
    # _output_stream: sounddevice.OutputStream = None

    def __init__(self, config: Config, params: Dictionary):
        self._parameters = params
        self._config = config
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()

        self.initialize()
    
    def initialize(self):
        language = self._parameters.get("language")
        model_name = self._config.get("text-to-speech.per_language." + language)
        self._model = self._config.get("storage.path") + "/" + self.MODELS_PATH + model_name + ".onnx"
        # self._voice = PiperVoice.load(self._model)
        # self._output_stream = sounddevice.OutputStream(samplerate=self._voice.config.sample_rate, channels=1, dtype='int16')
    
    # def say(self, text: str, input_stream_to_pause: sounddevice.RawInputStream = None):
    def say(self, text: str, input_stream_to_pause = None):

        import sounddevice
        from piper.voice import PiperVoice

        if self._config.get("text-to-speech.mock", True):
            self._logger.warning("Mocking TTS by Config. Should have said [" + text + "]")
        else:
            if input_stream_to_pause is not None:
                input_stream_to_pause.stop()

            self._logger.debug("Saying [" + text.replace("\n", "\\n") + "]")
            voice = PiperVoice.load(self._model)
            output_stream = sounddevice.OutputStream(samplerate=voice.config.sample_rate, channels=1, dtype='int16')
            output_stream.start()
            # self._output_stream.start()

            for audio_bytes in voice.synthesize_stream_raw(text):
                int_data = np.frombuffer(audio_bytes, dtype=np.int16)
                output_stream.write(int_data)
                # self._output_stream.write(int_data)

            output_stream.stop()
            # self._output_stream.stop()

            if input_stream_to_pause is not None:
                input_stream_to_pause.start()
    
    def terminate(self):
        # self._output_stream.close()
        pass