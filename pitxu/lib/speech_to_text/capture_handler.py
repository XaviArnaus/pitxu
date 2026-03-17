from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager, \
    SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY, SHARED_USER_IS_SPEAKING

import sys
import queue as Queue
from rms_vad import RmsVAD, VADConfig

class CaptureHandler(PyXavi):

    samplerate: int = 16000

    shared_memory: SharedMemoryManager = None
    queue: Queue.Queue = None
    vad: RmsVAD = None

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config, params: Dictionary):
        super(CaptureHandler, self).init_pyxavi(config=config, params=params)
    
        self._xlog.info("🗣️ Initializing Capture Handler for Speech-to-Text")

        if params.key_exists("capture_queue"):
            self.queue = params.get("capture_queue")
        
        else:
            raise ValueError("No capture queue provided in params to CaptureHandler")
        
        if params.key_exists("samplerate"):
            self.samplerate = params.get("samplerate")
        else:
            self._xlog.warning(f"No samplerate provided in params to CaptureHandler, using default of {self.samplerate} Hz")

        self.shared_memory = SharedMemoryManager(config=config, params=params)
        self.shared_memory.initialize_existing_shared_memory_flags()

        # Initialize the VAD with the provided configuration
        threshold = self._xconfig.get("speech-to-text.vad.threshold", 0.6)
        attack = self._xconfig.get("speech-to-text.vad.attack", 0.2)
        release = self._xconfig.get("speech-to-text.vad.release", 1.5)
        self.vad = RmsVAD(VADConfig(
            threshold=threshold, 
            attack=attack, # Last tests show that 0.0 attack (immediate detection) is the only that worked.
            release=release,
            sample_rate=self.samplerate
        ))
        self.vad.on_speech_start = lambda pre_buffer: self.vad_on_speech_start(pre_buffer)
        self.vad.on_audio = lambda chunk: self.vad_on_speech_chunk(chunk)
        self.vad.on_speech_end = lambda: self.vad_on_speech_end()
        # self.vad.
        self.log_summary("RMS VAD initialized", [
            ("Threshold", threshold),
            ("Attack", f"{attack} seconds"),
            ("Release", f"{release} seconds"),
            ("Sample Rate", f"{self.samplerate} Hz")
        ])

        self._log_debug("🗣️ Done Initializing Capture Handler for Speech-to-Text")
    
    def callback(self, indata, frames, time, status):
        """
        This is called (from a separate thread) for each audio block by the sounddevice library.
        Audio blocks are sentences.
        """
        if status:
            self._xlog.debug(f"🗣️ Audio input status: {status}")
            print(status, file=sys.stderr)

        if not self.should_skip_audio_input() and self.queue is not None:
            # self._xlog.debug(f"Input audio callback: Received audio block of {len(indata)} bytes, putting it in the queue for processing")
            # print(time.inputBufferAdcTime)

            # self.queue.put(bytes(indata))
            self.vad.feed(indata)
    
        # else:
        #     self._xlog.debug("Input audio callback: Skipping audio input, as the microphone is muted or the speaker is busy according to the shared memory flags")
    
    def vad_on_speech_start(self, pre_buffer: list[bytes]):
        self._xlog.debug("🗣️ VAD detected speech start")
        self.set_user_is_speaking()
        for frame in pre_buffer:
            self.queue.put(bytes(frame))
    
    def vad_on_speech_chunk(self, chunk: bytes):
        # self._xlog.debug(f"🗣️ VAD detected speech chunk of {len(chunk)} bytes")
        self.queue.put(bytes(chunk))
    
    def vad_on_speech_end(self):
        self._xlog.debug("🗣️ VAD detected speech end")
        self.unset_user_is_speaking()
        # Sending None as a marker for end of speech, so the recognizer can trigger an END step.
        self.queue.put(None)  # Using None as a marker for end of speech

        # TODO: ⚠️ This should actually trigger the whole Pitxu interaction pipeline.
    
    def get_vad_handler(self):
        return self.vad
    
    def should_skip_audio_input(self):
        '''
        Checks if the microphone is muted by reading AND if the speaker is talking via the shared memory flags
        '''

        speaker_is_busy = False
        mic_is_muted = False

        if self.shared_memory is None:
            self._xlog.error("🗣️ Shared Memory is None, cannot read 'SHARED_MICROPHONE_MUTED' flag")
            return False
        if (not isinstance(self.shared_memory.read_shared_memory_flag(SHARED_MICROPHONE_MUTED), bool)):
            self._xlog.error("🗣️ Shared Memory flag 3 should be 'SHARED_MICROPHONE_MUTED' but is not a boolean" + str(self.shared_memory.read_shared_memory_flag(SHARED_MICROPHONE_MUTED)))
            return False
        if (not isinstance(self.shared_memory.read_shared_memory_flag(SHARED_SPEAKER_BUSY), bool)):
            self._xlog.error("🗣️ Shared Memory flag 4 should be 'SHARED_SPEAKER_BUSY' but is not a boolean" + str(self.shared_memory.read_shared_memory_flag(SHARED_SPEAKER_BUSY)))
            return False
        mic_is_muted = self.shared_memory.read_shared_memory_flag(SHARED_MICROPHONE_MUTED)
        speaker_is_busy = self.shared_memory.read_shared_memory_flag(SHARED_SPEAKER_BUSY)

        return mic_is_muted or speaker_is_busy
    
    def set_user_is_speaking(self):
        """
        Sets the state to indicate that the user is currently speaking.
        Local flag, Shared memory flag, and ALWAYS resets the last human speaking datetime to now.
        """
        self.shared_memory.write_shared_memory_flag(SHARED_USER_IS_SPEAKING, True)
    
    def unset_user_is_speaking(self):
        """
        Unsets the state to indicate that the user is no longer speaking.
        Local flag, Shared memory flag, and ALWAYS nullifies the last human speaking datetime.
        """
        self.shared_memory.write_shared_memory_flag(SHARED_USER_IS_SPEAKING, False)
    
    def is_user_speaking(self) -> bool:
        """
        Checks if the user is currently speaking.
        Only Local based.
        """
        return self.shared_memory.read_shared_memory_flag(SHARED_USER_IS_SPEAKING)