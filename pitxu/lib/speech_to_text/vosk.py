import queue
import logging
import sys
import json

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary

from multiprocessing import shared_memory
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

    _shared_memory: shared_memory.ShareableList = None

    device = None
    samplerate = None

    def __init__(self, config: Config, params: Dictionary):
        self._parameters = params
        self._config = config
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()

        self.initialize()
    
    def initialize(self):

        self._logger.info("Initializing Vosk STT")

        language = self._parameters.get("language")
    
        if self._config.get("speech-to-text.mock", True):
            self._logger.info("Mocking Speech-to-Text by Config. Model not loaded.")
        else:
            self._model = Model(lang=language)

            self.samplerate = self._get_samplerate()
            self.device = self._config.get("speech-to-text.input_device", None)
        
            self._recognizer = KaldiRecognizer(self._model, self.samplerate)

        self._logger.info("Vosk: Creating queue to pass audio data to Vosk child process worker")
        self._queue = queue.Queue()
        self._logger.info("Vosk: Loading flags from Shared Memory")
        self._shared_memory = shared_memory.ShareableList(name=self._parameters.get("shared_memory_name"))
        if self._shared_memory is None:
            self._logger.error("Shared Memory is None, cannot read 'pause_mic' flag")

        self._logger.info("Done Initializing Vosk STT")
    
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
        
        if not self.is_mic_paused():
            self._queue.put(bytes(indata))

    def _int_or_str(self, text):
        """Helper function for argument parsing."""
        try:
            return int(text)
        except ValueError:
            return text
    
    def is_mic_paused(self):

        if self._shared_memory is None:
            self._logger.error("Shared Memory is None, cannot read 'pause_mic' flag")
            return False
        if (not isinstance(self._shared_memory[0], bool)):
            self._logger.error("Shared Memory flag 0 should be 'pause_mic' but is not a boolean" + self._shared_memory[0])
            return False
        
        return self._shared_memory[0]
        


        
