from pyxavi import Dictionary, Config, TerminalColor, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.support_process.support import Support
from pitxu.lib.utils.conversors import Conversors
from pitxu.lib.speech_to_text.state_machine import SttStateMachine, TrascriptionState
from pitxu.lib.speech_to_text.speech_to_text import SpeechToTextException
from pitxu.lib.speech_to_text.faster_whisper_stream_process import FasterWhisperStreamProcess
from pitxu.lib.utils.xprocess_pool import XprocessPool
from pitxu.lib.objects import XprocAction
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from definitions import SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY, SHARED_STT_BUSY, QUEUE_TRANSCRIBER, SHARED_TRANSCRIBER_BUSY, \
                        SHARED_DYNAMIC_RMS_SILENCE_THRESHOLD

import threading
import numpy as np
import queue
import time
import asyncio
from multiprocessing import JoinableQueue

try:
    import audioop
except ModuleNotFoundError:
    import audioop_lts as audioop

class FasterWhisperStream(PyXavi):
    """
    STT with Faster Whisper, with Streaming Window, partial merging and threading.

    - Works
    - Processes the audio chunks in the queue with a sliding window approach, while the user is still speaking.
    - Chunks are accummulated in a window of 40/50 chunks, overlapping last "n" samples (4000 samples = 250ms at 16kHz), merging text with some sort of string diff.
    - Fast enough. 
    - Way less accurate, some words are repeated, some words are cut, some words are wrong, ... 
        But the model afterwards understands it mostly (I want to avoid that it corrects it as much as possible).
    - Pitxu suggested to move to a Thread worker approach (2026-05-23).
    """

    _queue: queue.Queue = None
    _support: Support = None
    _faster_whisper_stream_process: FasterWhisperStreamProcess = None
    _shared_memory: SharedMemoryManager = None
    _stt_state_machine: SttStateMachine = None

    process_pool: XprocessPool = None

    transcriptor_input_queue: JoinableQueue = None
    transcriptor_output_queue: JoinableQueue = None
    on_transcription_finished_callback: callable = None

    # Queue used by the PreProcessor to calculate the dynamic RMS threshold for silence detection, based on the background noise level.
    silence_input_queue: JoinableQueue = None
    dynamic_rms: float = 0.0
    dynamic_rms_history: list[float] = []
    dynamic_rms_max_level: int = 32768  # maximum possible RMS for int16 audio (which is 32768)
    hysteresis_multiply: float = 1.05  # Multiplier for history percentage. Default 1.05.
    hysteresis_offset: float = 0.02  # Offset added to history percentage. Default 0.02.
    adapt_up_rate: float = 0.0025  # Threshold upward adaptation rate. Default 0.0025.
    adapt_down_rate: float = 1.0  # Threshold downward adaptation rate. Default 1.0.

    is_active: bool = False
    language: str = "en"

    _chunks_window = 10
    _sleep_when_no_chunks = 0.1

    _ongoing_chunk_window = []
    _worker_thread: threading.Thread = None
    final_transcription: str = ""
    ongoing_transcription: str = ""
    current_transcription_state: str = TrascriptionState.IDLE
    allow_chunk_consumption: bool = True

    # Be careful with this, other STT engines than FastgerWhisperStream don't support it and will fail.
    # It only relates to what CaptureHandler does. Other chunk queues do not use it by now.
    add_timestamps_to_chunks: bool = False
    # Be careful, it's not tuned and very aggressive. 
    # Drops some chunks that the model apparently can't tie the words together anymore, felling a drop in accuracy.
    # Calculating the RMS does not hurt... beyond the processing power (and that's why there is a flag to deactivate it).
    use_dynamic_rms_silence: bool = False

    VERBOSE_DEBUG: bool = True

    THREAD_NAME = "TranscriptorManager"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(FasterWhisperStream, self).init_pyxavi(config=config, params=params)

        self.initialize()
    
    def initialize(self):

        self._xlog.info("Initializing Faster Whisper Stream STT")
        logging_parts = []

        self.language = self._xparams.get("language", "en-us")
        # I need to correct this Vosk language stupidity that is populated all around the code!!!
        # if self.language == "en-us":
        #     self.language = "en"
        logging_parts.append(("Language", self.language if self.language != "en-us" else "en"))

        # Get the STT State Machine from params, fail otherwise.
        if self._xparams.key_exists("stt_state_machine"):
            self._stt_state_machine = self._xparams.get("stt_state_machine")
        else:
            raise ValueError("No STT State Machine provided in params to FasterWhisperStream class")

        # Get the callback for when the user finishes speaking, or use defaults.
        if self._xparams.key_exists("on_transcription_finished_callback"):
            self.on_transcription_finished_callback = self._xparams.get("on_transcription_finished_callback")
        else:
            raise ValueError("No callback provided for when the transcription finishes in params to CaptureHandler")
        
        # Get the callback's context for when the user finishes speaking, or use defaults.
        if self._xparams.key_exists("main_event_loop"):
            self.main_event_loop = self._xparams.get("main_event_loop")
        else:
            raise ValueError("No main event loop provided for when the user finishes speaking in params to CaptureHandler")
        
        # Get the process pool from params, fail otherwise.
        if self._xparams.key_exists("support"):
            self._support = self._xparams.get("support")
        else:
            raise ValueError("No Support class provided in params to FasterWhisperStreamV4 class")
        
        # Get the process pool from params, fail otherwise.
        if self._xparams.key_exists("process_pool"):
            self.process_pool = self._xparams.get("process_pool")
        else:
            raise ValueError("No XprocessPool provided in params to Support class")
        
        # The Silence Input Queue is created here, passed to the Transcriber Process (so it's forwarded to the PreProcessor)
        # and kept available here for the Main to retreive it and pass it to the CaptureHandler.
        self.silence_input_queue = self.process_pool.get_queue_manager().JoinableQueue()
        
        # Initialize the Faster Whisper Stream process in the pool, with the appropriate queues.
        initialized = self.process_pool.new_and_start(QUEUE_TRANSCRIBER, FasterWhisperStreamProcess, params=Dictionary({
            "initialize_from_main": False,
            "use_output_queue": True,
            "language": self.language,
            "support_class_queue": self._support.input_queue,
            "silence_input_queue": self.silence_input_queue
        }))
        if not initialized:
            raise RuntimeError("Failed to initialize FasterWhisperStreamProcess in the XprocessPool")
        
        self.transcriptor_input_queue = self.process_pool.get_queue(QUEUE_TRANSCRIBER)
        self.transcriptor_output_queue = initialized.get("output_queue")
        # self.transcriptor_output_queue_sentinel = initialized.get("sentinel_output_queue")

        if self._xconfig.get("speech-to-text.mock", True):
            self._xlog.info("Mocking Speech-to-Text by Config. Model not loaded.")
        else:
            chunks_window = int(self._xconfig.get("speech-to-text.faster_whisper_streaming.chunks_window", 10))
            sleep_when_no_chunks = float(self._xconfig.get("speech-to-text.faster_whisper_streaming.sleep_when_no_chunks", 0.1))

            self._chunks_window = chunks_window
            self._sleep_when_no_chunks = sleep_when_no_chunks

            logging_parts.append(("Chunks window", chunks_window))
            logging_parts.append(("Sleep when no chunks", sleep_when_no_chunks))
            logging_parts.append(("Dynamic RMS silence active", self.is_dynamic_rms_silence_active()))
            logging_parts.append(("Dynamic RMS max level", self.dynamic_rms_max_level))
            logging_parts.append(("Dynamic RMS hysteresis multiply", self.hysteresis_multiply))
            logging_parts.append(("Dynamic RMS hysteresis offset", self.hysteresis_offset))
            logging_parts.append(("Dynamic RMS adapt up rate", self.adapt_up_rate))
            logging_parts.append(("Dynamic RMS adapt down rate", self.adapt_down_rate))

            # We need to be able to receive a samplerate param so that the Server instance can operate a lower samplerate if needed,
            #   otherwise it will be forced to use the one from the microphone input, that has nothing to do with the external clients.
            # For normal local Pitxu, the chunk is downsampled in the CaptureHandler to 16kHz.
            # The choice is done in the calling:
            #   - For the Server, it is inside the Server initialisation from Main.
            #   - For the local Pitxu, it is inside the Params and Support initialisation from Main.
            #   > Both set a "samplerate" param, which value depends on one or another gathered in AudioParametersLoader.
            # self.samplerate = self._xparams.get("samplerate", None)
            # logging_parts.append(("Sample rate", self.samplerate))
            
            # self.device = self._xparams.get("audio_parameters.input_device", None)
            # logging_parts.append(("Input device", self.device))

        self._queue = queue.Queue()
        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory_flags()
        self._shared_memory.initialize_existing_shared_memory_values()

        # Keeping track that Whisper is active
        self.is_active = True
        self.current_transcription_state = TrascriptionState.IDLE
        self._log_debug("✏️ 👁️‍🗨️ Transcription state updated to IDLE 1st time, This is the beginning of the Transcriber.")
        self.allow_chunk_consumption = False
        logging_parts.append(("Initial transcription state", self.current_transcription_state.upper()))
        logging_parts.append(("Initial allow_chunk_consumption", self.allow_chunk_consumption))

        # We process all incoming chunks in a separate thread that continuously reads from the queue.
        self._worker_thread = threading.Thread(
            name=self.THREAD_NAME,
            target=self._transcription_worker,
            daemon=True)
        self._worker_thread.start()

        self.log_summary("Faster Whisper Stream Initialization", logging_parts)
    
    def get_queue(self) -> queue.Queue:
        return self._queue
    
    def get_silence_input_queue(self) -> JoinableQueue:
        return self.silence_input_queue
    
    def reset_context(self):

        # With this we:
        #   - Validate that we're in IDLE. Otherwise the transition will fail.
        #   - Validate that we want to go to START_CONTEXT. Otherwise the transition will fail.
        #   - If the transition is valid, it will update the state and return True. Otherwise, it will return False and not update the state.
        if self._stt_state_machine.transition_to(TrascriptionState.START_CONTEXT, expected_current_states=[TrascriptionState.IDLE]):
            self.allow_chunk_consumption = True
        else:
            current_state = self._stt_state_machine.get_transcription_state()
            self._xlog.warning(f"🟠 Reset Context invalid: Can't transition from {current_state}. Only IDLE state is allowed.")
            self.allow_chunk_consumption = False

        # Other vars
        self._ongoing_chunk_window = []
        self.final_transcription = ""
        self.ongoing_transcription = ""
        self.request_reset_context()
    
    def reset_context_and_state_in_transcription_thread(self):
        self._log_debug("Resetting transcription context and state in the transcription thread.")
        self._stt_state_machine.reset()
        self.allow_chunk_consumption = True
        self._ongoing_chunk_window = []
        self.final_transcription = ""
    
    def get_transcription(self) -> str:

        if self.final_transcription is not None and len(self.final_transcription) > 0:
            self._log_debug("Returning final transcription from cache.")
            return self.final_transcription
        else:
            self._xlog.warning("No transcription result available yet, you should not call this method from V4.")
    
    def get_transcription_status(self) -> str:
        return self._stt_state_machine.get_transcription_state()
    
    def _transcription_worker(self):
        """
        This is a worker that runs in a separate thread, that continuously processes the audio chunks in the queue 
        with a sliding window approach, while the user is still speaking.

        As we don't want to process chunk by chunk (they are too small for the Model), we need to accumulate the chunks in a window, 
        and process them together, with the context of the last overlap and the ongoing transcription.
        """

        # As the loop should consume the incoming chunks queue, the transcription result queue, and the silence input queue, 
        #   we need a set of flags.
        is_chunks_queue_empty: bool = False
        is_transcription_result_queue_empty: bool = False
        is_silence_input_queue_empty: bool = True
        chunk_list_to_process: list = []
        while self.is_active:
            try:
                # Get all current chunks on the queue. It should be only one,
                #   but we could have the following cases:
                #   - The user is speaking very fast and the VAD is sending chunks faster than we can process them.
                #   - It is the start of the VAD detection, that VAD adds some previous chunks as a window before the detection.
                #
                # Also, we get the transcription result if available.
                #   - When receiving a None chunk, we requuest the transcription result from the Process, and expect to receive it in the output queue. 
                #
                # So this loop is consuming 2 queues.

                # Work to be done if we have chunks in the chunks queue.
                if self._queue.empty():
                    is_chunks_queue_empty = True
                else:
                    is_chunks_queue_empty = False

                    # Get the next chunk from the queue.
                    if self.add_timestamps_to_chunks:
                        nanoseconds, data = self._queue.get()
                    else:
                        nanoseconds = None
                        data = self._queue.get()

                    if data is None:

                        # We need to make sure that the chunks that we receive belong to the current context.
                        # This is checked in the reset_context() method, that sets a flag to avoid consuming 
                        #   the chunks in the queue while we are in ONGOING_PROCESS_CHUNK or LEFTOVER_CHUNK_PROCESSING state, 
                        #   to avoid breaking the current transcription.
                        if not self.allow_chunk_consumption:
                            self._xlog.warning(f"🟠 Received audio chunk [None] while the transcription is not in a state to consume it. Current state: {self.current_transcription_state.upper()}.")
                            self._queue.task_done()
                            continue

                        self._log_debug("✏️ Received None data from the queue, It should be the end of the stream.")

                        # So the processing of all chunks is over, trigger the flush of all the audio dumps and plots, and clean it for next iterations.
                        self._support.dump_and_plot_all()
                        self._support.clear_accumulated_audio()

                        # It is very possible that we have chunks without process at this point.
                        if len(self._ongoing_chunk_window) > 0:

                            # Update the current state of the transcription
                            if not self._stt_state_machine.transition_to(TrascriptionState.LEFTOVER_CHUNK_PROCESSING, expected_current_states=[TrascriptionState.ONGOING_PROCESS_CHUNK]):
                                current_state = self._stt_state_machine.get_transcription_state()
                                self._xlog.warning(f"🟠 Received end of stream signal [None chunk] but can't transition from {current_state}to LEFTOVER_CHUNK_PROCESSING. Expected state was ONGOING_PROCESS_CHUNK.")

                            self._log_debug(f"✏️ Still {len(self._ongoing_chunk_window)} leftover audio chunks from the queue to process.")
                            self.process_chunks(self._ongoing_chunk_window)
                            self._ongoing_chunk_window = []
                        
                        # Clean anything LOCAL that would accumulate or trigger.
                        chunk_list_to_process = []

                        # Request the transcription result from the Process, and expect to receive it in the output queue.
                        # It is done like this because from the Process point of view, we don't know when the transcription actually finished.
                        self.request_transcription()

                        # Update the transcription state
                        if not self._stt_state_machine.transition_to(TrascriptionState.REQUESTED_TRANSCRIPTION, expected_current_states=[TrascriptionState.LEFTOVER_CHUNK_PROCESSING, TrascriptionState.ONGOING_PROCESS_CHUNK]):
                            current_state = self._stt_state_machine.get_transcription_state()
                            self._xlog.warning(f"🟠 Received end of stream signal [None chunk] but can't transition from {current_state} to REQUESTED_TRANSCRIPTION. Expected state was LEFTOVER_CHUNK_PROCESSING or ONGOING_PROCESS_CHUNK.")

                        # Reset the context in the Process, to be sure that the next transcription is not affected by the previous one.
                        self._ongoing_chunk_window = []
                        self.final_transcription = ""

                    else:

                        # We need to make sure that the chunks that we receive belong to the current context.
                        # This is checked in the reset_context() method, that sets a flag to avoid consuming 
                        #   the chunks in the queue while we are in ONGOING_PROCESS_CHUNK or LEFTOVER_CHUNK_PROCESSING state, 
                        #   to avoid breaking the current transcription.
                        if not self.allow_chunk_consumption:
                            current_state = self._stt_state_machine.get_transcription_state()
                            self._xlog.warning(f"🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: {current_state}.")
                            self._queue.task_done()
                            continue

                        # Update the current state of the transcription
                        if self._stt_state_machine.get_transcription_state() == TrascriptionState.ONGOING_PROCESS_CHUNK:
                            # We are already processing chunks, we just keep accumulating in the window.
                            pass
                        elif not self._stt_state_machine.transition_to(TrascriptionState.ONGOING_PROCESS_CHUNK, expected_current_states=[TrascriptionState.START_CONTEXT]):
                            # Try the transition and, if fails, dump a log.
                            current_state = self._stt_state_machine.get_transcription_state()
                            self._xlog.warning(f"🟠 Failed to transition to ONGOING_PROCESS_CHUNK. Current state: {current_state}.")

                        # Prepare the set of chunks to process
                        if len(self._ongoing_chunk_window) >= self._chunks_window:
                            self._log_debug(f"✏️ Ongoing chunk window exceeded the limit of {self._chunks_window} chunks. Processing.")
                            chunk_list_to_process.extend(self._ongoing_chunk_window.copy())
                            self._ongoing_chunk_window = []
                        self._ongoing_chunk_window.append(data)

                        # Process the prepared set of chunks
                        if len(chunk_list_to_process) > 0:
                            self._log_debug(f"✏️ Got {len(chunk_list_to_process)} audio chunks from the queue to process.")
                            self.process_chunks(chunk_list_to_process)
                            chunk_list_to_process = []
                    
                    self._queue.task_done()
                
                # Work to be done if we have a transcription result in the transcription result queue.
                if self.transcriptor_output_queue.empty():
                    is_transcription_result_queue_empty = True
                else:
                    is_transcription_result_queue_empty = False

                    # transcription_result = self.transcriptor_output_queue.get()

                    # partial_transcription = transcription_result.get("partial_transcription", None) if isinstance(transcription_result, dict) else None
                    # final_transcription = transcription_result.get("final_transcription", None) if isinstance(transcription_result, dict) else None

                    # It's a tuple: (partial, final).
                    # Both may be None.
                    partial_transcription, final_transcription = self.transcriptor_output_queue.get()

                    # If we have a partial, share it in the values to be caught by whoever wants it.
                    if partial_transcription is not None and len(partial_transcription) > 0:
                        self.ongoing_transcription = partial_transcription
                    
                    # If we don't receive a final transcription, means that we're still transcribing.
                    # There is no point on continuing the flow through the closing path.
                    if final_transcription is not None: 

                        # Update the current state of the transcription
                        if not self._stt_state_machine.transition_to(TrascriptionState.FINAL_TRANSCRIPTION, expected_current_states=[TrascriptionState.REQUESTED_TRANSCRIPTION]):
                            current_state = self._stt_state_machine.get_transcription_state()
                            self._xlog.warning(f"🟠 Received transcription result but can't transition from {current_state} to FINAL_TRANSCRIPTION. Expected state was REQUESTED_TRANSCRIPTION.")

                        if isinstance(final_transcription, str) and len(final_transcription) > 0:
                            self._log_debug(f"✏️ Got transcription result from the Process: {TerminalColor.RED}{final_transcription}{TerminalColor.END}")
                            # Oops! Why do we receive duplications?
                            if final_transcription in self.final_transcription:
                                self._log_debug("✏️ Received transcription result is already in the final transcription, skipping to avoid duplication.")
                            else:
                                self._log_debug("✏️ Merging transcription result with the final transcription.")
                                # self.final_transcription += " " + transcription_result
                                self.final_transcription = final_transcription
                            
                            # Update the current state of the transcription
                            if not self._stt_state_machine.transition_to(TrascriptionState.DONE, expected_current_states=[TrascriptionState.FINAL_TRANSCRIPTION]):
                                current_state = self._stt_state_machine.get_transcription_state()
                                self._xlog.warning(f"🟠 Received transcription result but can't transition from {current_state} to DONE. Expected state was FINAL_TRANSCRIPTION.")
                            
                            # Trigger the callback to notify that the transcription is finished, if we have a transcription result, or if we received the sentinel, which means that the transcription is finished even if we don't have a result (it can happen if the user spoke but the Model couldn't transcribe anything, so it returns an empty string as a result, but it still sends the sentinel to indicate that it finished processing).
                            if self.on_transcription_finished_callback is not None and (self.final_transcription is not None and len(self.final_transcription) > 0):
                                self._log_debug("✏️ Triggering on_transcription_finished_callback callback after receiving transcription result from the Process.")
                                # Be careful, it's part of asyncio loop.
                                asyncio.run_coroutine_threadsafe(self.on_transcription_finished_callback(self.final_transcription), self.main_event_loop)
                                # At this point, we should have the transcription queue empty, but sometimes we receive the transcription result again.
                                #   Then, the callback is called twice, making the whole chatbot & TTS to be repeated.
                                if not self.transcriptor_output_queue.empty():
                                    self._xlog.warning(f"Transcription was called and the queue should be empty, but it's not. Current length: {self.transcriptor_output_queue.qsize()}.")
                                    while not self.transcriptor_output_queue.empty():
                                        discarded_result = self.transcriptor_output_queue.get()
                                        self._xlog.warning(f"Discarding transcription result from the queue to avoid duplication: {discarded_result}")
                                    self._xlog.debug("Transcription queue is now empty after discarding results to avoid duplication.")

                        else:
                            self._log_debug("✏️  Got empty final transcription from the Process, skipping and bringing to IDLE.")
                    
                        # Update the current state of the transcription
                        # We expect here that the state comes from:
                        #   - FINAL_TRANSCRIPTION, if we received a transcription result, but it's empty, so no DONE state in between.
                        #   - DONE, if we received a transcription result with content, so we triggered the callback.
                        if not self._stt_state_machine.transition_to(TrascriptionState.IDLE, expected_current_states=[TrascriptionState.FINAL_TRANSCRIPTION, TrascriptionState.DONE]):
                            current_state = self._stt_state_machine.get_transcription_state()
                            self._xlog.warning(f"🟠 Received transcription result but can't transition to IDLE. Current state: {current_state}. Expected one of: {[TrascriptionState.FINAL_TRANSCRIPTION, TrascriptionState.DONE]}")


                        # And now we can set the flag to allow consuming chunks again, as we are in IDLE state.
                        self.allow_chunk_consumption = True
                        self._shared_memory.write_shared_memory_flag(SHARED_TRANSCRIBER_BUSY, False)

                    self.transcriptor_output_queue.task_done()
                
                # Work to be done if we have chunks in the Silence Input Queue, to calculate the dynamic RMS threshold for silence detection.
                if self.is_dynamic_rms_silence_active():
                    # Be careful, it's not tuned and very aggressive. 
                    # Drops some chunks that the model apparently can't tie the words together anymore, felling a drop in accuracy.
                    # Calculating the RMS does not hurt... beyond the processing power (and that's why there is a flag to deactivate it).
                    if self.silence_input_queue.empty():
                        is_silence_input_queue_empty = True
                    else:
                        is_silence_input_queue_empty = False

                        silence_chunk = self.silence_input_queue.get()
                        self.process_silence_chunk(silence_chunk)
                        self.silence_input_queue.task_done()
                
                if is_chunks_queue_empty and is_transcription_result_queue_empty and is_silence_input_queue_empty:
                    # Sleep for a short time to avoid busy waiting, and to give time to the other threads to add chunks to the queue.
                    time.sleep(self._sleep_when_no_chunks)

            except queue.Empty:
                continue
            except queue.ShutDown as e:
                self.is_active = False
                raise SpeechToTextException("Queue Shutdown detected in FasterWhisper Stream recognize(): " + str(e))
            except SpeechToTextException as ve:
                self.is_active = False
                # It's handled in Main, don't even log it here
                raise ve
            except KeyboardInterrupt:
                self._xlog.debug("Pressed Control + C while running FasterWhisper Stream transcription.")
                self.is_active = False
                self.close()
            except BrokenPipeError as bpe:
                self.is_active = False
                raise SpeechToTextException("FasterWhisper Stream BrokenPipeError: " + str(bpe))
            except Exception as e:
                self._xlog.error("🛑 Error during FasterWhisper Stream recognition: " + str(e))
                self._xlog.error(full_stack())
                self.close()
                return None
    
    def process_silence_chunk(self, chunk: bytes):
        """
        Once we know (from the VAD in CaptureHandler) that the chunk is not coming from human speaking,
        we can feed it to this function that will maintain the level of background noise, so the preprocess_chunk() can use it
        to remove silences.
        This comes from the issue on the silence at the end of the speech, that needs to be silence to be detected as the end of the speech,
        but makes the Transcriptor crazy, provoking hallucinations.
        """

        # The conversion to mono is done with Numnpy arrays for performance reasons, so convert it first.
        audio_data_np = Conversors.byte_chunk_to_numpy_array(chunk)
        audio_data_np = Conversors.stereo_to_mono(audio_data_np)

        # Calculates and merged the value into the dynamic RMS threshold for silence detection.
        # What is sample_width = 2? # 16 bits = 2 bytes
        rms = audioop.rms(audio_data_np.tobytes(), 2)

        # Maintain a history of RMS values for the last "n" silence chunks.
        self.dynamic_rms_history.append(rms)
        if len(self.dynamic_rms_history) > 100:
            self.dynamic_rms_history.pop(0)

        # Calculate the percentage through history
        history_average = (sum(self.dynamic_rms_history) / (len(self.dynamic_rms_history)))
        history_percentage = (history_average / self.dynamic_rms_max_level) * self.hysteresis_multiply + self.hysteresis_offset

        # Merging the current RMS with the previous dynamic RMS in the percentage defined in self.dynamic_rms_percent_to_apply_on_new_chunks,
        # to have a more stable value that is not changing so much with each chunk.
        if self.dynamic_rms <= 0:
            self.dynamic_rms = history_percentage
            return
        if history_percentage > self.dynamic_rms:
            # Slow rise - avoids false positives from transient noise
            self.dynamic_rms += (
                (history_percentage - self.dynamic_rms) * self.adapt_up_rate
            )
        elif history_percentage < self.dynamic_rms:
            # Fast drop - quickly adapts to quieter environments
            self.dynamic_rms += (
                (history_percentage - self.dynamic_rms) * self.adapt_down_rate
            )
        
        # Now we have to update the shared memory value with the new dynamic RMS threshold for silence detection,
        # so the Preprocessor can use it in the preprocess_chunk() function to decide if a chunk is considered as silence or not.
        self._shared_memory.write_shared_memory_value(SHARED_DYNAMIC_RMS_SILENCE_THRESHOLD, self.dynamic_rms)
    
    def is_dynamic_rms_silence_active(self) -> bool:
        # Be careful, it's not tuned and very aggressive. 
        # Drops some chunks that the model apparently can't tie the words together anymore, felling a drop in accuracy.
        return self.use_dynamic_rms_silence and self.silence_input_queue is not None
    
    def get_ongoing_transcription(self) -> str:
        return self.ongoing_transcription
    
    def close(self):
        self._xlog.info("Closing FasterWhisper Stream STT")

        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._xlog.debug("Waiting for FasterWhisper Stream thread to finish...")
            self.is_active = False
            self._worker_thread.join(timeout=2)
            if self._worker_thread.is_alive():
                self._xlog.warning("FasterWhisper Stream thread did not finish in time, it may be stuck. Moving on with closing.")
            else:
                self._xlog.debug("FasterWhisper Stream thread finished successfully.")
        
        if self._faster_whisper_stream_process is not None:
            self._xlog.debug("Closing FasterWhisper Stream process and deleting it")
            self.process_pool.send(QUEUE_TRANSCRIBER, XprocAction.FINISH)
            self.process_pool.wait_for_queue_to_empty(QUEUE_TRANSCRIBER)
            self._shared_memory.wait_for_busy_process_to_idle(SHARED_STT_BUSY)

            self._faster_whisper_stream_process.join(timeout=2)
            if self._faster_whisper_stream_process.is_alive():
                self._xlog.warning("FasterWhisper Stream process did not finish in time, it may be stuck. Moving on with closing.")
            del self._faster_whisper_stream_process
        
        if self._queue is not None:
            self._xlog.debug("Deleting FasterWhisper Stream queue")
            del self._queue
        
        if self.silence_input_queue is not None:
            # Joining queue to make sure that all tasks are done before closing.
            self._xlog.debug("Joining FasterWhisper Stream silence input queue to make sure all tasks are done before closing.")
            if not self.silence_input_queue.empty():
                while not self.silence_input_queue.empty():
                    discarded_chunk = self.silence_input_queue.get()
                    self.silence_input_queue.task_done()
                self.silence_input_queue.join()
            self._xlog.debug("Deleting FasterWhisper Stream silence input queue")
            del self.silence_input_queue
        
        # COMMENTED: The Support class is passed through params, so it does not belong to the FasterWhisperStream,
        # and it should be closed and deleted from the Main, as it's shared between several components.
        # if self._support is not None:
        #     self._xlog.debug("Closing Support process from FasterWhisper Stream and deleting it")
        #     del self._support
        
        # COMMENTED: Shared memory should only be closed from XProcessPool.close() (so, by the Interaction.close()),
        #   otherwise the memory is tried to be closed several times.
        # if self._shared_memory is not None:
        #     self._xlog.debug("Closing Shared Memory from FasterWhisper Stream")
        #     self._shared_memory.close()
        #     del self._shared_memory
        
        # Remember that FasterWhisper Stream is not active anymore
        self.is_active = False

        self._xlog.info("FasterWhisper Stream STT closed")
    
    def set_stt_busy(self):
        """
        Sets the shared memory flag to indicate that the STT is busy processing audio, so that the Speaker can wait if needed.
        """
        self._shared_memory.write_shared_memory_flag(SHARED_STT_BUSY, True)

    def unset_stt_busy(self):
        """
        Unsets the shared memory flag to indicate that the STT is not busy anymore, so that the Speaker can speak if needed.
        """
        self._shared_memory.write_shared_memory_flag(SHARED_STT_BUSY, False)
    
    def is_microphone_muted(self) -> bool:
        return self._shared_memory.read_shared_memory_flag(SHARED_MICROPHONE_MUTED)
    
    def is_speaker_busy(self) -> bool:
        return self._shared_memory.read_shared_memory_flag(SHARED_SPEAKER_BUSY)
    
    def process_chunks(self, chunks: list[bytes]) -> str:
        self._log_debug("Sending chunks window to be transcribed into the process")
        self.process_pool.send(QUEUE_TRANSCRIBER, XprocAction.TRANSCRIBE_CHUNK_WINDOW, chunks)
    
    def process_leftover_chunks(self) -> str:
        self._log_debug("Sending leftover chunks to be transcribed into the process")
        self.process_pool.send(QUEUE_TRANSCRIBER, XprocAction.TRANSCRIBE_LEFTOVER_CHUNKS)
    
    def request_transcription(self) -> str:
        self._log_debug("Requesting transcription result from the process")
        self.process_pool.send(QUEUE_TRANSCRIBER, XprocAction.RETRIEVE_TRANSCRIPTION_RESULT)
    
    def request_reset_context(self):
        self._log_debug("Requesting context reset in the process")
        self.process_pool.send(QUEUE_TRANSCRIBER, XprocAction.RESET_TRANSCRIPTION)
    
# 2. Dynamic Threshold Logic
# Instead of a static value, calculate it based on the background noise floor:
#    Formula: Threshold = NoiseFloor + (SensitivityFactor  NoiseVariance)
#    Implementation: Keep a running average of the RMS during "silent" periods. The SensitivityFactor is your "tuning knob"—if it's too aggressive, increase it slightly.

# 3. Hangover (Hold Time) Logic
# This prevents the "chopping" effect at the end of words:
#    State Machine:
#        If CurrentRMS > Threshold: Set IsSpeaking = True, reset HangoverTimer.
#        If CurrentRMS < Threshold:
#            If IsSpeaking is True: Start HangoverTimer.
#            If HangoverTimer exceeds your limit (for example, 300ms): Set IsSpeaking = False.
#    Why this works: It keeps the "gate" open during natural pauses between words or syllables, preventing the transcription model from thinking the sentence has ended prematurely.

# A quick tip for debugging:
# If you are still getting hallucinations, it might be because the "Hangover" is too long, and it's including too much background noise after you finish speaking. Try starting with a 250ms hold time and adjust from there.