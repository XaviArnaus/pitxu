import queue
import logging
import sys
import json

from pyxavi import Dictionary, Config, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from definitions import SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY

import whisper
import sounddevice as sd
import numpy as np

class WhisperException(Exception):
    pass

class Whisper(PyXavi):

    _queue: queue.Queue = None

    _shared_memory: SharedMemoryManager = None

    device: str = None
    samplerate: int = None
    model: whisper.Whisper = None

    is_active: bool = False

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Whisper, self).init_pyxavi(config=config, params=params)

        self.initialize()
    
    def initialize(self):

        self._xlog.info("Initializing Whisper STT")

        # unused?
        # language = self._xparams.get("language")

        if self._xconfig.get("speech-to-text.mock", True):
            self._xlog.info("Mocking Speech-to-Text by Config. Model not loaded.")
        else:
            model = self._xconfig.get("speech-to-text.whisper.model", "base")
            self._xlog.info(f"Whisper: Loading model from config: {model}")
            self.model = whisper.load_model(name=model, in_memory=True)

            self.samplerate = self._get_samplerate()
            self.device = self._xconfig.get("speech-to-text.input_device", None)
            self._xlog.debug(f"Whisper: Samplerate {self.samplerate}, Device {self.device}")

        self._xlog.info("Whisper: Creating queue to pass audio data to Whisper child process worker")
        self._queue = queue.Queue()
        self._xlog.info("Whisper: Loading flags from Shared Memory")
        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory_flags()

        # Keeping track that Whisper is active
        self.is_active = True

        self._xlog.info("Done Initializing Whisper STT")
    
    def recognize(self) -> str:
        try:
            if self._xconfig.get("speech-to-text.mock", True):
                return input("Type your question: [\"exit\" to leave]: \n")
            elif self.is_active == False:
                raise WhisperException("Whisper is not active, cannot recognize audio")
            elif self.is_active and self._queue is not None:
                data = self._queue.get()
                recognize_outcome = self.process_audio_chunk(data)
                dd(recognize_outcome)
                # Since Whisper can return both partial and final results, for normal "local" Pitxu
                #   we completely ignore the partial.
                if recognize_outcome.get("result") is not None:
                    result = recognize_outcome.get("result")
                    if recognize_outcome.get("final") is not None and len(recognize_outcome.get("final")) > 0:
                        result = result + " " + recognize_outcome.get("final")
                    return result
        except queue.ShutDown as e:
            self.is_active = False
            raise WhisperException("Queue Shutdown detected in Whisper recognize(): " + str(e))
        except WhisperException as we:
            self.is_active = False
            # It's handled in Main, don't even log it here
            raise we
        except BrokenPipeError as bpe:
            self.is_active = False
            raise WhisperException("Whisper BrokenPipeError: " + str(bpe))
        except Exception as e:
            self._xlog.error("🛑 Error during Whisper recognition: " + str(e))
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

        # Get the numpy version of these bytes.
        audio_np = np.frombuffer(data, dtype=np.int16)

        # Convert the numpy array to float32 and normalize
        audio_float32 = audio_np.flatten().astype('float32') / 32768.0

        # Transcribe the audio chunk
        result = self.model.transcribe(audio_float32)
        dd(result)
        transcription = result["text"]
        if transcription is not None and transcription.strip() != "":
            self._log_debug(f"Whisper: Recognized text: [{transcription}]")
            outcome["result"] = transcription.strip()
        
        return outcome
    
    def reset_result(self):
        """
        This appears not to be needed for Whisper, but the Server endpoint calls it and by now we leave it.
        """
        pass
    
    def _get_samplerate(self) -> int:
        samplerate = self._xconfig.get("speech-to-text.whisper.input_samplerate", None)
        if samplerate is not None:
            self._xlog.debug(f"Whisper: Using samplerate from config: {samplerate}")
        else:
            device_info = sd.query_devices(self.device, "input")
            samplerate = device_info["default_samplerate"]
            self._xlog.debug(f"Whisper: Using samplerate from device: {samplerate}")

        # soundfile expects an int, sounddevice provides a float:
        return int(samplerate)

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
        self._xlog.info("Closing Whisper STT")

        if self.model is not None:
            self._xlog.debug("Deleting Whisper model")
            del self.model
        
        if self._queue is not None:
            self._xlog.debug("Deleting Whisper queue")
            del self._queue
        
        # Remember that Whisper is not active anymore
        self.is_active = False

        self._xlog.info("Whisper STT closed")


        
