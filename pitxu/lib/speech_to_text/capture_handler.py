from functools import partial

from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.utils.conversors import Conversors
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager, \
    SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY, SHARED_VAD_DETECTED

import sys
import queue as Queue
from rms_vad import RmsVAD, VADConfig
import numpy as np
import logging
import samplerate
import asyncio

class CaptureHandler(PyXavi):

    microphone_samplerate: int = 16000
    target_samplerate: int = 16000

    shared_memory: SharedMemoryManager = None
    queue: Queue.Queue = None
    vad: RmsVAD = None
    resampler: samplerate.Resampler = None
    on_vad_detected_started_callback: callable = None
    on_vad_detected_ongoing_callback: callable = None
    on_vad_detected_finished_callback: callable = None
    main_event_loop: asyncio.AbstractEventLoop = None

    local_vad_detected: bool = False

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config, params: Dictionary):
        super(CaptureHandler, self).init_pyxavi(config=config, params=params)
    
        self._xlog.info("🗣️ Initializing Capture Handler for Speech-to-Text")

        # Get the capture queue from params, fail otherwise.
        if params.key_exists("capture_queue"):
            self.queue = params.get("capture_queue")
        else:
            raise ValueError("No capture queue provided in params to CaptureHandler")
        
        # Get the microphone samplerate from params, or use defaults.
        if params.key_exists("microphone_samplerate"):
            self.microphone_samplerate = params.get("microphone_samplerate")
        else:
            self._xlog.warning(f"No samplerate provided in params to CaptureHandler, using default of {self.microphone_samplerate} Hz")

        # Get the target samplerate from params, or use defaults.
        if params.key_exists("target_samplerate"):
            self.target_samplerate = params.get("target_samplerate")
        else:
            self._xlog.warning(f"No target samplerate provided in params to CaptureHandler, using default of {self.target_samplerate} Hz")

        # Get the callback for when the user finishes speaking, or use defaults.
        if params.key_exists("on_vad_detected_finished_callback"):
            self.on_vad_detected_finished_callback = params.get("on_vad_detected_finished_callback")
        else:
            raise ValueError("No callback provided for when the user finishes speaking in params to CaptureHandler")
        
        # Get the callback for when the user starts speaking, or use defaults.
        if params.key_exists("on_vad_detected_started_callback"):
            self.on_vad_detected_started_callback = params.get("on_vad_detected_started_callback")
        else:
            raise ValueError("No callback provided for when the user starts speaking in params to CaptureHandler")
        
        # Get the callback for when the user is speaking, or use defaults.
        if params.key_exists("on_vad_detected_ongoing_callback"):
            self.on_vad_detected_ongoing_callback = params.get("on_vad_detected_ongoing_callback")
        else:
            raise ValueError("No callback provided for when the user is speaking in params to CaptureHandler")

        # Get the callback's context for when the user finishes speaking, or use defaults.
        if params.key_exists("main_event_loop"):
            self.main_event_loop = params.get("main_event_loop")
        else:
            raise ValueError("No main event loop provided for when the user finishes speaking in params to CaptureHandler")

        # Control for `is_vad_detected` flag.
        self.shared_memory = SharedMemoryManager(config=config, params=params)
        self.shared_memory.initialize_existing_shared_memory_flags()

        # Initialize the VAD with the provided configuration
        threshold = self._xconfig.get("speech-to-text.vad.threshold", 0.6)
        attack = self._xconfig.get("speech-to-text.vad.attack", 0.2)
        release = self._xconfig.get("speech-to-text.vad.release", 1.5)
        chunksize = self._xconfig.get("speech-to-text.blocksize", 1024)
        self.vad = RmsVAD(VADConfig(
            threshold=threshold, 
            attack=attack, # Last tests show that 0.0 attack (immediate detection) is the only that worked.
            release=release,
            sample_rate=self.target_samplerate,
            chunk_size=chunksize
        ))
        self.vad.on_speech_start = lambda pre_buffer: self.vad_on_speech_start(pre_buffer)
        self.vad.on_audio = lambda chunk: self.vad_on_speech_chunk(chunk)
        self.vad.on_speech_end = lambda: self.vad_on_speech_end()

        self.log_summary("RMS VAD initialized", [
            ("Enabled", str(self._xconfig.get("speech-to-text.vad.enabled", False))),
            ("Threshold", threshold),
            ("Attack", f"{attack} seconds"),
            ("Release", f"{release} seconds"),
            ("Sample Rate", f"{self.target_samplerate} Hz"),
            ("Chunk Size", f"{chunksize} samples")
        ])

        self.resampler = samplerate.Resampler(converter_type='sinc_best')
        
        self.log_summary(f"Resampler will {'not be used' if self.microphone_samplerate == self.target_samplerate else 'resample audio'}", [
            ("In Sample Rate", f"{self.microphone_samplerate} Hz"),
            ("Out Sample Rate", f"{self.target_samplerate} Hz")
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

            # Whatever comes as input, resample it to the working samplerate.
            if self.microphone_samplerate != self.target_samplerate:
                # indata = Conversors.resample_audio_interpolation(indata, 
                #                                     in_rate=self.microphone_samplerate, 
                #                                     out_rate=self.target_samplerate)
                indata = Conversors.resample_audio_scikit(self.resampler,
                                            indata,
                                            in_rate=self.microphone_samplerate,
                                            out_rate=self.target_samplerate)
                
                # Sometimes the resampled audio can be empty due to some issue in the resampling process, so we check for that before feeding the VAD.
                if len(indata) == 0 or indata is None:
                    self._xlog.warning("🗣️ Resampled audio is None or empty, skipping this block")
                    return


            if self._xconfig.get("speech-to-text.vad.enabled", False):
                # Feed the VAD, it will decide if has a speech,
                # and put the chunk into the queue via callbacks.
                self.vad.feed(indata)
            else:
                self.queue.put(bytes(indata))
    
        # else:
        #     self._xlog.debug("Input audio callback: Skipping audio input, as the microphone is muted or the speaker is busy according to the shared memory flags")
    
    def vad_on_speech_start(self, pre_buffer: list[bytes]):
        self._xlog.debug("🗣️ VAD detected speech start")
        self.set_vad_detected()
        for frame in pre_buffer:
            self.queue.put(bytes(frame))
        
        # Now we can trigger the main execution, as the user has started speaking.
        if self.on_vad_detected_started_callback is not None:
            asyncio.run_coroutine_threadsafe(self.on_vad_detected_started_callback(), self.main_event_loop)
        else:
            self._xlog.warning("🗣️ No callback provided for when the user starts speaking, but VAD detected speech start. Please provide an 'on_vad_detected_started_callback' in the params of CaptureHandler to handle this event.")
    
    def vad_on_speech_chunk(self, chunk: bytes):
        # self._xlog.debug(f"🗣️ VAD detected speech chunk of {len(chunk)} bytes")
        self.queue.put(bytes(chunk))

        # Now we can trigger the main execution, as the user is speaking.
        if self.on_vad_detected_ongoing_callback is not None:
            asyncio.run_coroutine_threadsafe(self.on_vad_detected_ongoing_callback(), self.main_event_loop)
        else:
            self._xlog.warning("🗣️ No callback provided for when the user is speaking, but VAD detected speech chunk. Please provide an 'on_vad_detected_ongoing_callback' in the params of CaptureHandler to handle this event.")
    
    def vad_on_speech_end(self):
        self._xlog.debug("🗣️ VAD detected speech end")
        self.unset_vad_detected()

        # Sending None as a marker for end of speech, so the recognizer can trigger an END step.
        self.queue.put(None)

        # Now we can trigger the main execution, as the user has finished speaking.
        if self.on_vad_detected_finished_callback is not None:
            asyncio.run_coroutine_threadsafe(self.on_vad_detected_finished_callback(), self.main_event_loop)
        else:
            self._xlog.warning("🗣️ No callback provided for when the user finishes speaking, but VAD detected speech end. Please provide an 'on_vad_detected_finished_callback' in the params of CaptureHandler to handle this event."
)
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
    
    def set_vad_detected(self):
        """
        Sets the state to indicate that the user is currently speaking.
        Local flag, Shared memory flag, and ALWAYS resets the last human speaking datetime to now.
        """
        self.shared_memory.write_shared_memory_flag(SHARED_VAD_DETECTED, True)
    
    def unset_vad_detected(self):
        """
        Unsets the state to indicate that the user is no longer speaking.
        Local flag, Shared memory flag, and ALWAYS nullifies the last human speaking datetime.
        """
        self.shared_memory.write_shared_memory_flag(SHARED_VAD_DETECTED, False)
    
    def is_vad_detected(self) -> bool:
        """
        Checks if the user is currently speaking.
        Only Local based.
        """
        return self.shared_memory.read_shared_memory_flag(SHARED_VAD_DETECTED)