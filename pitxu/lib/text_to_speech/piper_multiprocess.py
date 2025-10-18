from multiprocessing import Process, Queue
import numpy as np
import sounddevice
from piper.voice import PiperVoice

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary

import logging

from pitxu.lib.dto import QueueItemType, QueueItemAction

# Trying here to make a Worker for Multiprocessing.
class PiperMultiprocess(Process):

    MODELS_PATH = "tts_models/"

    _config: Config = None
    _logger: logging = None
    _parameters: Dictionary = None

    _queue: Queue = None

    _model: None
    _voice: None
    _output_stream: sounddevice.OutputStream = None

    def __init__(self, config: Config, params: Dictionary, queue: Queue):
        self._parameters = params
        self._config = config
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()

        self._queue = queue

        self.initialize()

        super(PiperMultiprocess, self).__init__()
    
    def initialize(self):
        language = self._parameters.get("language")
        model_name = self._config.get("text-to-speech.per_language." + language)
        self._model = self._config.get("storage.path") + "/" + self.MODELS_PATH + model_name + ".onnx"
        self._voice = PiperVoice.load(self._model)
        self._output_stream = sounddevice.OutputStream(samplerate=self._voice.config.sample_rate, channels=1, dtype='int16')
    
    def run(self):
        for (type, message) in iter(self.task_queue.get, None):
            self._logger.debug("Piper Worker received a [" + type + "]: [" + message + "]")
            if type == QueueItemType.MESSAGE and message != "":
                self.say(message)
                self._queue.task_done() # <-- Notify queue that task is complete
            if type == QueueItemType.ACTION and message == QueueItemAction.TERMINATE:
                self.terminate()
                
    
    def say(self, text: str):

        if self._config.get("text-to-speech.mock", True):
            self._logger.warning("Mocking TTS by Config. Should have said [" + text + "]")
        else:
            self._logger.debug("Saying [" + text.replace("\n", "\\n") + "]")
            self._output_stream.start()

            for audio_bytes in self._voice.synthesize_stream_raw(text):
                int_data = np.frombuffer(audio_bytes, dtype=np.int16)
                self._output_stream.write(int_data)

            self._output_stream.stop()
    
    def terminate(self):
        self._output_stream.close()