import queue
import logging
import sys
import json

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary

from vosk import Model, KaldiRecognizer
import sounddevice as sd

class Vosk:

    ENGLISH: str = "en-us"
    CATALAN: str = "ca"
    GERMAN: str = "de"
    SPANISH: str = "es"

    _config: Config = None
    _logger: logging = None
    _parameters: Dictionary = None

    _model = None
    _queue = None
    _recognizer: KaldiRecognizer = None

    device = None
    samplerate = None

    def __init__(self, config: Config, params: Dictionary):
        self._parameters = params
        self._config = config
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()

        self.initialize()
    
    def initialize(self, language: str = None):
        if language is None:
            language = self._config.get("speech-to-text.default_language", self.ENGLISH)
    
        self._queue = queue.Queue()
        self._model = Model(lang=language)

        self.samplerate = self._get_samplerate()
        self.device = self._config.get("speech-to-text.input_device", None)
    
        self._recognizer = KaldiRecognizer(self._model, self.samplerate)
    
    def recognize(self) -> str:
        if self._config.get("speech-to-text.mock", True):
            return input("Type your question: [\"exit\" to leave]: \n")
        else:
            data = self._queue.get()
            if self._recognizer.AcceptWaveform(data):
                result = json.loads(self._recognizer.Result())
                self._logger.info("Recognized text: " + result["text"].replace("\n", ""))
                return result["text"]
            else:
                result = json.loads(self._recognizer.PartialResult())
                # self._logger.debug("Recognized partial: " + result["partial"].replace("\n", ""))
                return None
    
    def _get_samplerate(self) -> int:
        device_info = sd.query_devices(self.device, "input")
        # soundfile expects an int, sounddevice provides a float:
        return int(device_info["default_samplerate"])

    def callback(self, indata, frames, time, status):
        """This is called (from a separate thread) for each audio block."""
        if status:
            # self._logger.debug("Finished audio block, status is " + status)
            print(status, file=sys.stderr)
        self._queue.put(bytes(indata))

    def _int_or_str(self, text):
        """Helper function for argument parsing."""
        try:
            return int(text)
        except ValueError:
            return text
        

        
