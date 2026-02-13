import queue
import sys

from pyxavi import Dictionary, Config, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.microservice.client import Client
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from definitions import SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY
import sounddevice as sd

class SpeechToTextException(Exception):
    pass

class SpeechToText(PyXavi):

    ENGLISH: str = "en-us"
    CATALAN: str = "ca"
    GERMAN: str = "de"
    SPANISH: str = "es"

    _queue: queue.Queue = None
    _shared_memory: SharedMemoryManager = None
    _client: Client = None

    device = None
    samplerate = None

    is_active: bool = False

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(SpeechToText, self).init_pyxavi(config=config, params=params)
    
    def initialize(self):

        self._xlog.info("Initializing SpeechToText")

        if self._xconfig.get("speech-to-text.mock", True):
            self._xlog.info("Mocking Speech-to-Text by Config. Model not loaded.")
        else:
            self.samplerate = self._get_samplerate()
            self.device = self._xconfig.get("speech-to-text.input_device", None)
            self._xlog.debug(f"STT: Samplerate {self.samplerate}, Device {self.device}")

            self._client = Client(config=self._xconfig, params=self._xparams)
            self._client.initialize()

        self._xlog.info("STT: Creating queue to pass audio data to SpeechToText child process worker")
        self._queue = queue.Queue()
        self._xlog.info("STT: Loading flags from Shared Memory")
        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory_flags()

        # Keeping track that SpeechToText is active
        self.is_active = True

        self._xlog.info("Done Initializing SpeechToText")
    
    def recognize(self) -> str | None:
        try:
            if self._xconfig.get("speech-to-text.mock", True):
                return input("Type your question: [\"exit\" to leave]: \n")
            elif self.is_active == False:
                raise SpeechToTextException("SpeechToText is not active, cannot recognize audio")
            elif self.is_active and self._queue is not None:
                # data = self._queue.get()
                # Since we now have to PUSH TO TALK, we may don't need this
                # if len(data) <= 1024:
                #     return None
                self._log_debug("Getting recorded audio bytes from the queue...")
                audio_bytes = self.build_recorded_audio_bytes()
                self._log_debug(f"Transcribing {len(audio_bytes)} bytes of audio data from the queue")
                return self.get_transcription(audio_bytes)
        except queue.ShutDown as e:
            self.is_active = False
            raise SpeechToTextException("Queue Shutdown detected in SpeechToText recognize(): " + str(e))
        except SpeechToTextException as stte:
            self.is_active = False
            # It's handled in Main, don't even log it here
            raise stte
        except BrokenPipeError as bpe:
            self.is_active = False
            raise SpeechToTextException("SpeechToText BrokenPipeError: " + str(bpe))
        except Exception as e:
            self._xlog.error("🛑 Error during SpeechToText recognition: " + str(e))
            self._xlog.error(full_stack())
            self.close()
            return None
    
    def get_transcription(self, data: bytes):
        """
        Method to be called to process audio data received from the microphone input or the server endpoint.
        """

        if self._client is None:
            raise SpeechToTextException("SpeechToText client is not initialized, cannot process audio data")
        
        server_answer = self._client.transcribe(data_bytes=data)
        if server_answer["error"] is not None:
            error_message = server_answer.get("error")
            raise SpeechToTextException(f"Error from STT server: {error_message}")
        
        if server_answer["transcription"] is None:
            self._log_debug("STT server returned no transcription")
            return None

        result_text = str(server_answer["transcription"]).replace("\n", "").strip()
        if result_text == "":
            self._log_debug("STT server returned empty transcription")
            return None

        self._xlog.debug(f"*️⃣ SpeechToText: Recognized text: {result_text}")
        return result_text
        
    
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
            self._xlog.debug(f"*️⃣ Audio input status: {status}")

        if not self.should_skip_audio_input() and self._queue is not None:
            # print(time.inputBufferAdcTime)
            self._queue.put(bytes(indata))
    
    def build_recorded_audio_bytes(self) -> bytes:
        """
        Utility method to build the recorded audio bytes from the queue.
        It will keep getting data from the queue until it's empty and concatenate it into a single bytes object.
        """
        audio_bytes = b""
        if self._queue is not None:
            while not self._queue.empty():
                audio_bytes += self._queue.get()
        return audio_bytes
    
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
        self._xlog.info("Closing SpeechToText")
        
        if self._queue is not None:
            self._xlog.debug("Deleting SpeechToText queue")
            del self._queue
        
        # Remember that SpeechToText is not active anymore
        self.is_active = False

        self._xlog.info("SpeechToText closed")


        
