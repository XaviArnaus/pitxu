from functools import partial

from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.speech_to_text.state_machine import SttStateMachine, TrascriptionState
from pitxu.lib.utils.conversors import Conversors
from pitxu.lib.utils.xtime import Xtime
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager, \
    SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY, SHARED_VAD_DETECTED, SHARED_TRANSCRIBER_BUSY

import sys
import queue as Queue
from rms_vad import RmsVAD, VADConfig
from rms_vad.events import VADEventType, VADEvent
import numpy as np
import logging
import samplerate
import asyncio
import threading

class CaptureHandler(PyXavi):

    microphone_samplerate: int = 16000
    target_samplerate: int = 16000

    shared_memory: SharedMemoryManager = None
    # Queue to put the chunks that the Raw Input Stream produces, in the initial callback.
    queue: Queue.Queue = None
    # Internal queue to communicate the decoupled Input Stream with the VAD callbacks, to avoid putting non-speech chunks in the main queue. 
    internal_queue: Queue.Queue = None
    vad: RmsVAD = None
    resampler: samplerate.Resampler = None
    on_vad_detected_started_callback: callable = None
    on_vad_detected_ongoing_callback: callable = None
    on_vad_detected_finished_callback: callable = None
    main_event_loop: asyncio.AbstractEventLoop = None
    stt_state_machine: SttStateMachine = None

    is_active: bool = True

    vad_thread: threading.Thread = None

    # Be careful with this, other STT engines than FastgerWhisperStream don't support it and will fail.
    add_timestamps_to_chunks: bool = False

    VERBOSE_DEBUG: bool = False
    THREAD_NAME = "VADWorker"

    def __init__(self, config: Config, params: Dictionary):
        super(CaptureHandler, self).init_pyxavi(config=config, params=params)
    
        self._xlog.info("🗣️ Initializing Capture Handler for Speech-to-Text")

        # Get the STT State Machine from params, fail otherwise.
        if self._xparams.key_exists("stt_state_machine"):
            self.stt_state_machine = self._xparams.get("stt_state_machine")
        else:
            raise ValueError("No STT State Machine provided in params to FasterWhisperStream class")

        # Get the capture queue from params, fail otherwise.
        if params.key_exists("capture_queue"):
            self.queue = params.get("capture_queue")
        else:
            raise ValueError("No capture queue provided in params to CaptureHandler")
        
        # Get the silence input queue from params, or simply deactivate the dynamic RMS silence threshold if not provided.
        if params.key_exists("silence_input_queue"):
            self.silence_input_queue = params.get("silence_input_queue")
        else:
            self._xlog.warning("No silence input queue provided in params to CaptureHandler, Dynamic RMS Silence threshold deactivated")
        
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

        # The intermediate queue to communicate the decoupled Input Stream with the VAD callbacks
        self.internal_queue = Queue.Queue()

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
            ("Chunk Size", f"{chunksize} samples"),
            ("Dynamic RMS Silence Detection Active", f"{"Yes" if self._is_silence_dynamic_rms_active() else "No"}")
        ])

        self.resampler = samplerate.Resampler(converter_type='sinc_best')
        
        self.log_summary(f"Resampler will {'not be used' if self.microphone_samplerate == self.target_samplerate else 'resample audio'}", [
            ("In Sample Rate", f"{self.microphone_samplerate} Hz"),
            ("Out Sample Rate", f"{self.target_samplerate} Hz")
        ])

        self._xlog.debug("🗣️ Starting VAD worker thread to process raw audio chunks from the Input Stream...")
        self.vad_thread = threading.Thread(target=self._process_raw_chunks_worker, name=self.THREAD_NAME, daemon=True)
        self.vad_thread.start()

        self._log_debug("🗣️ Done Initializing Capture Handler for Speech-to-Text")
    
    def close(self):
        self._xlog.info("🗣️ Closing Capture Handler for Speech-to-Text")

        self.is_active = False

        # Empty the intermediate queue
        self._xlog.debug("Emptying internal queue of Capture Handler...")
        while not self.internal_queue.empty():
            try:
                self.internal_queue.get_nowait()
                self.internal_queue.task_done()
            except Queue.Empty:
                pass

        # Now join the queue
        self._xlog.debug("Joining internal queue of Capture Handler...")
        self.internal_queue.join()

        # Now joing the thread
        self._xlog.debug("Joining VAD worker thread of Capture Handler...")
        if self.vad_thread is not None:
            self.vad_thread.join()

        # Now finish the VAD
        self._xlog.debug("Closing VAD of Capture Handler...")
        if self.vad is not None:
            self.vad.reset()
            del self.vad

        # And also the Resampler
        self._xlog.debug("Closing Resampler of Capture Handler...")
        if self.resampler is not None:
            del self.resampler

        # COMMENTED: Shared memory should only be closed from XProcessPool.close() (so, by the Interaction.close()),
        #   otherwise the memory is tried to be closed several times.
        # if self.shared_memory is not None:
        #     self._xlog.debug("Closing Shared Memory from Capture Handler")
        #     self.shared_memory.close()
        #     del self.shared_memory

        self._log_debug("🗣️ Done Closing Capture Handler for Speech-to-Text")
    
    def _is_silence_dynamic_rms_active(self) -> bool:
        return self.silence_input_queue is not None
    
    def callback(self, indata, frames, time, status):
        """
        This is called (from a separate thread) for each audio block by the sounddevice library.
        Audio blocks are sentences.
        """
        if status:
            self._xlog.debug(f"🗣️ Audio input status: {status}")
            print(status, file=sys.stderr)
        
        # Now we simply put the chunk in an intermediate queue to be processed by the VAD worker, 
        # to avoid doing heavy processing in this callback and risking to block the audio input.
        self.internal_queue.put(bytes(indata))
    
        # else:
        #     self._xlog.debug("Input audio callback: Skipping audio input, as the microphone is muted or the speaker is busy according to the shared memory flags")
    
    def _process_raw_chunks_worker(self):
        """
        This is a worker that runs in a separate thread, to process the raw chunks that the Input Stream produces and put them in the main queue if they are detected as speech by the VAD.
        This is necessary to decouple the Input Stream thread from the VAD processing, to avoid blocking the Input Stream thread with the VAD processing.
        """
        while self.is_active:

            if self.internal_queue.empty():
                continue  # No chunk to process, loop again

            chunk = self.internal_queue.get(timeout=1)  # Wait for a chunk for up to 1 second
            if chunk is None:
                continue  # Skip if we receive a None chunk, which can be used as a signal to stop the worker
            
            if not self.should_skip_audio_input() and self.queue is not None and self.is_active:
                # self._xlog.debug(f"Input audio callback: Received audio block of {len(chunk)} bytes, putting it in the queue for processing")

                # Whatever comes as input, resample it to the working samplerate.
                if self.microphone_samplerate != self.target_samplerate:
                    # chunk = Conversors.resample_audio_interpolation(chunk, 
                    #                                     in_rate=self.microphone_samplerate, 
                    #                                     out_rate=self.target_samplerate)
                    chunk = Conversors.resample_audio_scikit(self.resampler,
                                                chunk,
                                                in_rate=self.microphone_samplerate,
                                                out_rate=self.target_samplerate)
                    
                    # Sometimes the resampled audio can be empty due to some issue in the resampling process, so we check for that before feeding the VAD.
                    if len(chunk) == 0 or chunk is None:
                        self._xlog.warning("🗣️ Resampled audio is None or empty, skipping this block")
                        continue

                vad_returned_events = []
                if self._xconfig.get("speech-to-text.vad.enabled", False):
                    # Feed the VAD, it will decide if has a speech,
                    # and put the chunk into the queue via callbacks.
                    vad_returned_events = self.vad.feed(chunk)
                else:
                    if self.add_timestamps_to_chunks:
                        queue_data = (Xtime.now_as_milliseconds(), bytes(chunk))
                    else:
                        queue_data = bytes(chunk)
                    self.queue.put(queue_data)
                
                # Now, depending on what the VAD returned, we can identify if that was a speech or not.
                if self._is_silence_dynamic_rms_active() and not self._vad_event_is_speech_chunk(vad_returned_events):
                    # VAD did not detect that this chunk is part of a speech,
                    # we put it in the silence input queue for the Preprocessor to analyze its RMS.
                    # self._xlog.debug("🗣️ VAD did not detect speech in this chunk, putting it in the silence input queue for dynamic RMS calculation")
                    self.silence_input_queue.put(bytes(chunk))
            
            self.internal_queue.task_done()
    
    def _vad_event_is_speech_chunk(self, events: list[VADEvent]) -> bool:
        if len(events) == 0 or events is None:
            return False
        for event in events:
            if event.type in [VADEventType.SPEECH_START, VADEventType.AUDIO]:
                return True
        return False

    def vad_on_speech_start(self, pre_buffer: list[bytes]):
        if not self.is_active:
            self._xlog.debug("🗣️ VAD detected speech start, but CaptureHandler is not active, ignoring.")
            return
        
        if not self.stt_state_machine.is_valid_expected_current_state(TrascriptionState.IDLE):
            self._xlog.warning(f"🟠 VAD detected speech start but the current state is not IDLE: {self.stt_state_machine.get_transcription_state()}")
            return

        self._xlog.debug("🗣️ VAD detected speech start")
        self.set_vad_detected()
        for frame in pre_buffer:
            if self.add_timestamps_to_chunks:
                queue_data = (Xtime.now_as_milliseconds(), bytes(frame))
            else:
                queue_data = bytes(frame)
            self.queue.put(queue_data)
        
        # Now we can trigger the main execution, as the user has started speaking.
        if self.on_vad_detected_started_callback is not None:
            asyncio.run_coroutine_threadsafe(self.on_vad_detected_started_callback(), self.main_event_loop)
        else:
            self._xlog.warning("🗣️ No callback provided for when the user starts speaking, but VAD detected speech start. Please provide an 'on_vad_detected_started_callback' in the params of CaptureHandler to handle this event.")
    
    def vad_on_speech_chunk(self, chunk: bytes):
        if not self.is_active:
            self._xlog.debug("🗣️ VAD detected speech chunk, but CaptureHandler is not active, ignoring.")
            return
        
        if not self.stt_state_machine.is_valid_expected_current_states([TrascriptionState.START_CONTEXT, TrascriptionState.ONGOING_PROCESS_CHUNK]):
            self._xlog.warning(f"🟠 VAD detected speech chunk but current state is {self.stt_state_machine.get_transcription_state()}. Expected one of: {[TrascriptionState.START_CONTEXT, TrascriptionState.ONGOING_PROCESS_CHUNK]}. Ignoring this chunk.")
            return

        # self._xlog.debug(f"🗣️ VAD detected speech chunk of {len(chunk)} bytes")
        if self.add_timestamps_to_chunks:
            queue_data = (Xtime.now_as_milliseconds(), bytes(chunk))
        else:
            queue_data = bytes(chunk)
        self.queue.put(queue_data)

        # Now we can trigger the main execution, as the user is speaking.
        if self.on_vad_detected_ongoing_callback is not None:
            asyncio.run_coroutine_threadsafe(self.on_vad_detected_ongoing_callback(), self.main_event_loop)
        else:
            self._xlog.warning("🗣️ No callback provided for when the user is speaking, but VAD detected speech chunk. Please provide an 'on_vad_detected_ongoing_callback' in the params of CaptureHandler to handle this event.")
    
    def vad_on_speech_end(self):
        if not self.is_active:
            self._xlog.debug("🗣️ VAD detected speech end, but CaptureHandler is not active, ignoring.")
            return
        
        if not self.stt_state_machine.is_valid_expected_current_states([TrascriptionState.START_CONTEXT, TrascriptionState.ONGOING_PROCESS_CHUNK]):
            self._xlog.warning(f"🟠 VAD detected speech end but current state is {self.stt_state_machine.get_transcription_state()}. Expected one of: {[TrascriptionState.START_CONTEXT, TrascriptionState.ONGOING_PROCESS_CHUNK]}. Ignoring this event.")
            return

        self._xlog.debug("🗣️ VAD detected speech end")
        self.unset_vad_detected()

        # Sending None as a marker for end of speech, so the recognizer can trigger an END step.
        if self.add_timestamps_to_chunks:
            queue_data = (Xtime.now_as_milliseconds(), None)
        else:
            queue_data = None
        self.queue.put(queue_data)

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
        Checks if the microphone is muted OR if the speaker is busy via the shared memory flags
        '''

        if self.shared_memory is not None:
            mic_is_muted = self.shared_memory.read_shared_memory_flag(SHARED_MICROPHONE_MUTED)
            speaker_is_busy = self.shared_memory.read_shared_memory_flag(SHARED_SPEAKER_BUSY)

            return any([mic_is_muted, speaker_is_busy])
        else:
            # no shared memory, avoid putting any chunk in any queue, to avoid triggering any process.
            return True
    
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