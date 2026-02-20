import queue
import logging
import sys
import json

from pyxavi import Dictionary, Config, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from definitions import SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY

from vosk import Model, KaldiRecognizer, SetLogLevel
import sounddevice as sd

class VoskException(Exception):
    pass

class Vosk(PyXavi):

    ENGLISH: str = "en-us"
    CATALAN: str = "ca"
    GERMAN: str = "de"
    SPANISH: str = "es"

    _model: Model = None
    _queue: queue.Queue = None
    _recognizer: KaldiRecognizer = None

    _shared_memory: SharedMemoryManager = None

    device = None
    samplerate = None

    is_active: bool = False

    VERBOSE_DEBUG: bool = True
    VOICE_LIB_LOG_LEVEL: int = 0

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Vosk, self).init_pyxavi(config=config, params=params)

        self.initialize()
    
    def initialize(self):

        self._xlog.info("Initializing Vosk STT")

        language = self._xparams.get("language")

        if self._xconfig.get("speech-to-text.mock", True):
            self._xlog.info("Mocking Speech-to-Text by Config. Model not loaded.")
        else:
            # Set the log levels for the Gemini API client and httpcore libraries based on the configuration
            self.VOICE_LIB_LOG_LEVEL = self._xconfig.get("libs_logger.vosk.loglevel", self.VOICE_LIB_LOG_LEVEL)
            self._log_debug("Setting Vosk client log level to: " + str(self.VOICE_LIB_LOG_LEVEL))
            SetLogLevel(self._xconfig.get("speech-to-text.internal_logging", self.VOICE_LIB_LOG_LEVEL))

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

        # Keeping track that Vosk is active
        self.is_active = True

        self._xlog.info("Done Initializing Vosk STT")
    
    def recognize(self) -> str:
        try:
            if self._xconfig.get("speech-to-text.mock", True):
                return input("Type your question: [\"exit\" to leave]: \n")
            elif self.is_active == False:
                raise VoskException("Vosk is not active, cannot recognize audio")
            elif self.is_active and self._queue is not None:
                data = self._queue.get()
                recognize_outcome = self.process_audio_chunk(data)
                # Since Vosk can return both partial and final results, for normal "local" Pitxu
                #   we completely ignore the partial.
                if recognize_outcome.get("result") is not None:
                    result = recognize_outcome.get("result")
                    if recognize_outcome.get("final") is not None and len(recognize_outcome.get("final")) > 0:
                        result = result + " " + recognize_outcome.get("final")
                    return result
        except queue.ShutDown as e:
            self.is_active = False
            raise VoskException("Queue Shutdown detected in Vosk recognize(): " + str(e))
        except VoskException as ve:
            self.is_active = False
            # It's handled in Main, don't even log it here
            raise ve
        except BrokenPipeError as bpe:
            self.is_active = False
            raise VoskException("Vosk BrokenPipeError: " + str(bpe))
        except Exception as e:
            self._xlog.error("🛑 Error during Vosk recognition: " + str(e))
            self._xlog.error(full_stack())
            self.close()
            return None
    
    def process_audio_chunk(self, data: bytes) -> str | None:
        """
        Method to be called to process audio data received from the microphone input or the server endpoint.
        """
        outcome = {
            "result": None,
            "partial": None,
            "final": None
        }
        if self._recognizer.AcceptWaveform(data):
            result = json.loads(self._recognizer.Result())
            result_text = str(result["text"]).replace("\n", "").strip()
            if result_text == "":
                outcome["result"] = None
            else:
                self._xlog.debug(f"Vosk: Recognized text: [{result_text}]")
                outcome["result"] = result_text

            if self._recognizer.FinalResult():
                result = json.loads(self._recognizer.FinalResult())
                result_text = str(result["text"]).replace("\n", "").strip()
                if result_text == "":
                    outcome["final"] = None
                else:
                    self._xlog.debug(f"Vosk: Final recognized text: [{result_text}]")
                    outcome["final"] = result_text
            
        else:
            result = json.loads(self._recognizer.PartialResult())
            outcome["partial"] = str(result["partial"]).replace("\n", "").strip()

        return outcome
    
    def reset_result(self):
        """
        Method to reset the Vosk recognizer result. This is needed to avoid having old transcriptions in the next calls.
        It is used in the server endpoint after processing a transcription, to clean the Vosk state for the next transcription.
        """
        self._recognizer.Reset()

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

        if not self.should_skip_audio_input() and self._queue is not None:
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

    def close(self):
        self._xlog.info("Closing Vosk STT")

        if self._recognizer is not None:
            self._xlog.debug("Deleting Vosk recognizer")
            del self._recognizer
        
        if self._model is not None:
            self._xlog.debug("Deleting Vosk model")
            del self._model
        
        if self._queue is not None:
            self._xlog.debug("Deleting Vosk queue")
            del self._queue
        
        # Remember that Vosk is not active anymore
        self.is_active = False

        self._xlog.info("Vosk STT closed")


        
