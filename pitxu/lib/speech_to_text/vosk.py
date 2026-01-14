import queue
import logging
import sys
import json

from pyxavi import Dictionary, Config
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from definitions import SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY

from vosk import Model, KaldiRecognizer, SetLogLevel
import sounddevice as sd

class Vosk(PyXavi):

    ENGLISH: str = "en-us"
    CATALAN: str = "ca"
    GERMAN: str = "de"
    SPANISH: str = "es"

    _model = None
    _queue = None
    _recognizer: KaldiRecognizer = None

    _shared_memory: SharedMemoryManager = None

    device = None
    samplerate = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Vosk, self).init_pyxavi(config=config, params=params)

        self.initialize()
    
    def initialize(self):

        self._xlog.info("Initializing Vosk STT")

        language = self._xparams.get("language")

        if self._xconfig.get("speech-to-text.mock", True):
            self._xlog.info("Mocking Speech-to-Text by Config. Model not loaded.")
        else:
            SetLogLevel(self._xconfig.get("speech-to-text.internal_logging", 0))

            model = self._xconfig.get("speech-to-text.model." + language, None)
            if model is not None:
                self._xlog.info("Vosk: Loading model from config: " + model)
                self._model = Model(model_name=model)
            else:
                self._xlog.info("Vosk: Loading default model for language: " + language)
                self._model = Model(lang=language)

            self.samplerate = self._get_samplerate()
            self.device = self._xconfig.get("speech-to-text.input_device", None)
            self._xlog.debug(f"Vosk: Samplerate {self.samplerate}, Device {self.device}")

            self._xlog.debug("Vosk: initializing KaldiRecognizer")
            self._recognizer = KaldiRecognizer(self._model, self.samplerate)

        self._xlog.info("Vosk: Creating queue to pass audio data to Vosk child process worker")
        self._queue = queue.Queue()
        self._xlog.info("Vosk: Loading flags from Shared Memory")
        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory_flags()

        self._xlog.info("Done Initializing Vosk STT")
    
    def recognize(self) -> str:
        if self._xconfig.get("speech-to-text.mock", True):
            return input("Type your question: [\"exit\" to leave]: \n")
        else:
            data = self._queue.get()
            if self._recognizer.AcceptWaveform(data):
                result = json.loads(self._recognizer.Result())
                result_text = str(result["text"]).replace("\n", "").strip()
                if result_text == "":
                    return None
                self._xlog.debug(f"Vosk: Recognized text: {result_text}")
                return result_text
            else:
                result = json.loads(self._recognizer.PartialResult())
                return None
    
    def _get_samplerate(self) -> int:
        device_info = sd.query_devices(self.device, "input")
        # soundfile expects an int, sounddevice provides a float:
        return int(device_info["default_samplerate"])

    def callback(self, indata, frames, time, status):
        """
        This is called (from a separate thread) for each audio block.
        Audio blocks are sentences.
        """
        if status:
            print(status, file=sys.stderr)
        
        if not self.should_skip_audio_input():
            # print(time.inputBufferAdcTime)
            self._queue.put(bytes(indata))

    def _int_or_str(self, text):
        """Helper function for argument parsing."""
        try:
            return int(text)
        except ValueError:
            return text
    
    def should_skip_audio_input(self):
        '''
        Checks if the microphone is muted by reading AND if the speaker is talking via the shared memory flags
        '''

        speaker_is_busy = False
        mic_is_muted = False

        if self._shared_memory is None:
            self._xlog.error("Shared Memory is None, cannot read 'SHARED_MICROPHONE_MUTED' flag")
            return False
        if (not isinstance(self._shared_memory.read_shared_memory_flag(SHARED_MICROPHONE_MUTED), bool)):
            self._xlog.error("Shared Memory flag 3 should be 'SHARED_MICROPHONE_MUTED' but is not a boolean" + str(self._shared_memory.read_shared_memory_flag(SHARED_MICROPHONE_MUTED)))
            return False
        if (not isinstance(self._shared_memory.read_shared_memory_flag(SHARED_SPEAKER_BUSY), bool)):
            self._xlog.error("Shared Memory flag 4 should be 'SHARED_SPEAKER_BUSY' but is not a boolean" + str(self._shared_memory.read_shared_memory_flag(SHARED_SPEAKER_BUSY)))
            return False
        mic_is_muted = self._shared_memory.read_shared_memory_flag(SHARED_MICROPHONE_MUTED)
        speaker_is_busy = self._shared_memory.read_shared_memory_flag(SHARED_SPEAKER_BUSY)

        return mic_is_muted or speaker_is_busy


        
