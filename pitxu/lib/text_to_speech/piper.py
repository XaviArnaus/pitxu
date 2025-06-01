import numpy as np
import sounddevice
from piper.voice import PiperVoice

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary

import logging

class Piper:

    MODELS_PATH = "tts_models/"

    _config: Config = None
    _logger: logging = None
    _parameters: Dictionary = None

    _model: None
    _voice: None

    def __init__(self, config: Config, params: Dictionary):
        self._parameters = params
        self._config = config
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()

        self.initialize()
    
    def initialize(self):
        language = self._config.get("text-to-speech.default_language")
        model_name = self._config.get("text-to-speech.per_language." + language)
        self._model = self._config.get("storage.path") + "/" + self.MODELS_PATH + model_name + ".onnx"
        self._voice = PiperVoice.load(self._model)
    
    def say(self, text: str):
        self._logger.debug("Saying [" + text.replace("\n", "\\n") + "]")
        stream = sounddevice.OutputStream(samplerate=self._voice.config.sample_rate, channels=1, dtype='int16')
        stream.start()

        for audio_bytes in self._voice.synthesize_stream_raw(text):
            int_data = np.frombuffer(audio_bytes, dtype=np.int16)
            stream.write(int_data)

        stream.stop()
        stream.close()