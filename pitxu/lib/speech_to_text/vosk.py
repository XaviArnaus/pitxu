import queue
import logging
import sys
import json

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary
from definitions import SHARED_SPEAKER_BUSY

from multiprocessing import shared_memory
from vosk import Model, KaldiRecognizer
import sounddevice as sd

class Vosk:

    ENGLISH: str = "en-us"
    CATALAN: str = "ca"
    GERMAN: str = "de"
    SPANISH: str = "es"

    _xconfig: Config = None
    _xlog: logging = None
    _xparams: Dictionary = None

    _model = None
    _queue = None
    _recognizer: KaldiRecognizer = None

    _shared_memory: shared_memory.ShareableList = None

    device = None
    samplerate = None

    def __init__(self, config: Config, params: Dictionary):
        self._xparams = params
        self._xconfig = config
        self._xlog = Logger(config=config, base_path=self._xparams.get("base_path", "")).get_logger()

        self.initialize()
    
    def initialize(self):

        self._xlog.info("Initializing Vosk STT")

        language = self._xparams.get("language")
    
        if self._xconfig.get("speech-to-text.mock", True):
            self._xlog.info("Mocking Speech-to-Text by Config. Model not loaded.")
        else:
            self._model = Model(lang=language)

            self.samplerate = self._get_samplerate()
            self.device = self._xconfig.get("speech-to-text.input_device", None)
        
            self._recognizer = KaldiRecognizer(self._model, self.samplerate)

        self._xlog.info("Vosk: Creating queue to pass audio data to Vosk child process worker")
        self._queue = queue.Queue()
        self._xlog.info("Vosk: Loading flags from Shared Memory")
        self._shared_memory = shared_memory.ShareableList(name=self._xparams.get("shared_memory_name"))
        if self._shared_memory is None:
            self._xlog.error("Shared Memory is None, cannot read 'SHARED_SPEAKER_BUSY' flag")

        self._xlog.info("Done Initializing Vosk STT")
    
    def recognize(self) -> str:
        if self._xconfig.get("speech-to-text.mock", True):
            return input("Type your question: [\"exit\" to leave]: \n")
        else:
            data = self._queue.get()
            if self._recognizer.AcceptWaveform(data):
                result = json.loads(self._recognizer.Result())
                self._xlog.info("Recognized text: " + result["text"].replace("\n", ""))
                return result["text"]
            else:
                result = json.loads(self._recognizer.PartialResult())
                # self._xlog.debug("Recognized partial: " + result["partial"].replace("\n", ""))
                return None
    
    def _get_samplerate(self) -> int:
        device_info = sd.query_devices(self.device, "input")
        # soundfile expects an int, sounddevice provides a float:
        return int(device_info["default_samplerate"])

    def callback(self, indata, frames, time, status):
        """This is called (from a separate thread) for each audio block."""
        if status:
            # self._xlog.debug("Finished audio block, status is " + status)
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
            self._xlog.error("Shared Memory is None, cannot read 'SHARED_SPEAKER_BUSY' flag")
            return False
        if (not isinstance(self._shared_memory[SHARED_SPEAKER_BUSY], bool)):
            self._xlog.error("Shared Memory flag 0 should be 'SHARED_SPEAKER_BUSY' but is not a boolean" + self._shared_memory[SHARED_SPEAKER_BUSY])
            return False
        
        return self._shared_memory[SHARED_SPEAKER_BUSY]
        


        
