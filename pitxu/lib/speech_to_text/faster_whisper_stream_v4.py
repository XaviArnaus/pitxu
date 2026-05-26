from pyxavi import Dictionary, Config, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.support_process.support import Support
from pitxu.lib.speech_to_text.speech_to_text import SpeechToTextException
from pitxu.lib.speech_to_text.faster_whisper_stream_process import FasterWhisperStreamProcess
from pitxu.lib.utils.xprocess_pool import XprocessPool
from pitxu.lib.objects import XprocAction
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from definitions import SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY, SHARED_STT_BUSY, QUEUE_TRANSCRIBER

import threading
import queue
import time
import asyncio
from multiprocessing import JoinableQueue

class FasterWhisperStreamV4(PyXavi):
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

    process_pool: XprocessPool = None

    transcriptor_input_queue: JoinableQueue = None
    transcriptor_output_queue: JoinableQueue = None
    # transcriptor_output_queue_sentinel: object = None

    on_transcription_finished_callback: callable = None

    is_active: bool = False
    language: str = "en"

    # _beam_size = 5
    # _overlap_size = 2000
    _chunks_window = 10
    _sleep_when_no_chunks = 0.1
    # _use_low_confidence_threshold = False
    # _low_confidence_threshold = -1

    _ongoing_chunk_window = []
    _worker_thread: threading.Thread = None
    final_transcription: str = ""

    VERBOSE_DEBUG: bool = True

    THREAD_NAME = "TranscriptorManager"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(FasterWhisperStreamV4, self).init_pyxavi(config=config, params=params)

        self.initialize()
    
    def initialize(self):

        self._xlog.info("Initializing Faster Whisper Stream STT")
        logging_parts = []

        self.language = self._xparams.get("language", "en-us")
        # I need to correct this Vosk language stupidity that is populated all around the code!!!
        # if self.language == "en-us":
        #     self.language = "en"
        logging_parts.append(("Language", self.language if self.language != "en-us" else "en"))

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
        
        # Initialize the Faster Whisper Stream process in the pool, with the appropriate queues.
        initialized = self.process_pool.new_and_start(QUEUE_TRANSCRIBER, FasterWhisperStreamProcess, params=Dictionary({
            "initialize_from_main": False,
            "use_output_queue": True,
            "language": self.language,
            "support_class_queue": self._support.input_queue,
        }))
        if not initialized:
            raise RuntimeError("Failed to initialize FasterWhisperStreamProcess in the XprocessPool")
        
        self.transcriptor_input_queue = self.process_pool.get_queue(QUEUE_TRANSCRIBER)
        self.transcriptor_output_queue = initialized.get("output_queue")
        # self.transcriptor_output_queue_sentinel = initialized.get("sentinel_output_queue")

        if self._xconfig.get("speech-to-text.mock", True):
            self._xlog.info("Mocking Speech-to-Text by Config. Model not loaded.")
        else:
            # model = self._xconfig.get("speech-to-text.faster_whisper_streaming.model." + self.language, None)
            # if model is not None:
            #     # I don't understand why device and download_root get read as tuples instead of strings.
            #     device = str(self._xconfig.get("speech-to-text.faster_whisper_streaming.device", "cpu"))
            #     download_root = str(os.path.join(self._xconfig.get("storage.path"), self._xconfig.get("speech-to-text.faster_whisper_streaming.download_root", None)))
            #     compute_type = str(self._xconfig.get("speech-to-text.faster_whisper_streaming.compute_type", "int8"))
            #     beam_size = int(self._xconfig.get("speech-to-text.faster_whisper_streaming.beam_size", 5))
            #     overlap_size = int(self._xconfig.get("speech-to-text.faster_whisper_streaming.overlap_size", 2000))
            chunks_window = int(self._xconfig.get("speech-to-text.faster_whisper_streaming.chunks_window", 10))
            sleep_when_no_chunks = float(self._xconfig.get("speech-to-text.faster_whisper_streaming.sleep_when_no_chunks", 0.1))
            #     self._beam_size = beam_size
            #     self._overlap_size = overlap_size
            self._chunks_window = chunks_window
            self._sleep_when_no_chunks = sleep_when_no_chunks

            #     logging_parts.append(("Model from config", model))
            #     logging_parts.append(("Device for Faster Whisper", device))
            #     logging_parts.append(("Download root", download_root))
            #     logging_parts.append(("Compute type", compute_type))
            #     logging_parts.append(("Beam size", beam_size))
            #     logging_parts.append(("Overlap size", overlap_size))
            #     logging_parts.append(("Overlapping chunks duration at 16kHz (ms)", round(overlap_size / 16000 * 1000, 2)))
            logging_parts.append(("Chunks window", chunks_window))
            logging_parts.append(("Sleep when no chunks", sleep_when_no_chunks))
            #     self.log_summary("Faster Whisper Stream Model Initialization", logging_parts)
            # else:
            #     raise SpeechToTextException(f"No model specified in config for language {self.language}, and mocking is disabled, cannot initialize Faster Whisper STT.")

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

            # Forwarding the Support process to the Preprocessor via xparams,
            #   here just checking that it's there, for the log summary.
            # logging_parts.append(("Support class is present", "Yes" \
            #                       if self._xparams.key_exists("support") \
            #                         and self._xparams.get("support") is not None \
            #                         and isinstance(self._xparams.get("support"), Support) \
            #                       else "No"))

        self._queue = queue.Queue()
        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory_flags()

        # Keeping track that Whisper is active
        self.is_active = True

        # We process all incoming chunks in a separate thread that continuously reads from the queue.
        self._worker_thread = threading.Thread(
            name=self.THREAD_NAME,
            target=self._transcription_worker,
            daemon=True)
        self._worker_thread.start()

        self.log_summary("Faster Whisper Stream Initialization", logging_parts)
    
    def get_queue(self) -> queue.Queue:
        return self._queue
    
    def reset_context(self):
        self._ongoing_chunk_window = []
        self.final_transcription = ""
        self.request_reset_context()
    
    def get_transcription(self) -> str:

        if self.final_transcription is not None and len(self.final_transcription) > 0:
            self._log_debug("Returning final transcription from cache.")
            return self.final_transcription
        else:
            self._xlog.warning("No transcription result available yet, you should not call this method from V4.")
    
    def _transcription_worker(self):
        """
        This is a worker that runs in a separate thread, that continuously processes the audio chunks in the queue 
        with a sliding window approach, while the user is still speaking.

        As we don't want to process chunk by chunk (they are too small for the Model), we need to accumulate the chunks in a window, 
        and process them together, with the context of the last overlap and the ongoing transcription.
        """

        # As the loop should consume the incoming chunks queue and the transcription result queue, we need a set of flags.
        is_chunks_queue_empty = False
        is_transcription_result_queue_empty = False
        chunk_list_to_process = []
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
                    data = self._queue.get()

                    if data is None:
                        self._log_debug("FasterWhisper Stream: Received None data from the queue, It should be the end of the stream.")

                        # Process the leftover chunks in the window, if any, with the context of the last overlap and the ongoing transcription.
                        # COMMENTED: Feels like this is not needed, as the transcription appears complete until now in the logs and then, all of a sudden,
                        #   a lot of garbage is added at the end
                        # _ = self._process_leftover_chunks()

                        # So the processing of all chunks is over, trigger the flush of all the audio dumps and plots, and clean it for next iterations.
                        self._support.dump_and_plot_all()
                        self._support.clear_accumulated_audio()

                        # Clean anything LOCAL that would accumulate or trigger.
                        chunk_list_to_process = []

                        # Request the transcription result from the Process, and expect to receive it in the output queue.
                        # It is done like this because from the Process point of view, we don't know when the transcription actually finished.
                        self.request_transcription()

                    else:
                        if len(self._ongoing_chunk_window) >= self._chunks_window:
                            self._log_debug(f"FasterWhisper Stream: Ongoing chunk window exceeded the limit of {self._chunks_window} chunks. Processing.")
                            chunk_list_to_process.extend(self._ongoing_chunk_window.copy())
                            self._ongoing_chunk_window = []
                        self._ongoing_chunk_window.append(data)

                    if len(chunk_list_to_process) > 0:
                        self._log_debug(f"FasterWhisper Stream: Got {len(chunk_list_to_process)} audio chunks from the queue to process.")
                        self.process_chunks(chunk_list_to_process)
                        chunk_list_to_process = []
                
                # Work to be done if we have a transcription result in the transcription result queue.
                if self.transcriptor_output_queue.empty():
                    is_transcription_result_queue_empty = True
                else:
                    is_transcription_result_queue_empty = False

                    transcription_result = self.transcriptor_output_queue.get()

                    if isinstance(transcription_result, str) and len(transcription_result) > 0:
                        self._log_debug("FasterWhisper Stream: Got transcription result from the Process: " + transcription_result)
                        # Oops! Why do we receive duplications?
                        if transcription_result in self.final_transcription:
                            self._log_debug("FasterWhisper Stream: Received transcription result is already in the final transcription, skipping to avoid duplication.")
                        else:
                            self.final_transcription += " " + transcription_result

                    # elif transcription_result == self.transcriptor_output_queue_sentinel:
                    #     # Now we now that the result sending is finished. 
                    #     self._log_debug("Received sentinel from the Process.")
                        
                        # Trigger the callback to notify that the transcription is finished, if we have a transcription result, or if we received the sentinel, which means that the transcription is finished even if we don't have a result (it can happen if the user spoke but the Model couldn't transcribe anything, so it returns an empty string as a result, but it still sends the sentinel to indicate that it finished processing).
                        if self.on_transcription_finished_callback is not None and (self.final_transcription is not None and len(self.final_transcription) > 0):
                            self._log_debug("FasterWhisper Stream: Triggering on_transcription_finished_callback callback after receiving transcription result from the Process.")
                            # Be careful, it's part of asyncio loop.
                            asyncio.run_coroutine_threadsafe(self.on_transcription_finished_callback(self.final_transcription), self.main_event_loop)
                
                if is_chunks_queue_empty and is_transcription_result_queue_empty:
                    # Sleep for a short time to avoid busy waiting, and to give time to the other threads to add chunks to the queue.
                    time.sleep(self._sleep_when_no_chunks)
                
                # At this point in time, if we have any ongoing transcription,
                #  means that the STT identified a speech and is processing.
                # If we're processing chunks but there is no transcription, it means that 
                #   the chunks do not contain a speech.
                # COMMENTED: The ongoing transcription happens in the separate process.
                # if len(self._ongoing_transcription) > 0:
                #     self.set_stt_busy()
                # else:
                #     self.unset_stt_busy()

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
    
    def close(self):
        self._xlog.info("Closing FasterWhisper Stream STT")

        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._xlog.debug("Waiting for FasterWhisper Stream worker thread to finish...")
            self._worker_thread.join(timeout=2)
            if self._worker_thread.is_alive():
                self._xlog.warning("FasterWhisper Stream worker thread did not finish in time, it may be stuck. Moving on with closing.")
            else:
                self._xlog.debug("FasterWhisper Stream worker thread finished successfully.")
        
        if self._faster_whisper_stream_process is not None:
            self._xlog.debug("Closing FasterWhisper Stream process and deleting it")
            self._faster_whisper_stream_process.join(timeout=2)
            if self._faster_whisper_stream_process.is_alive():
                self._xlog.warning("FasterWhisper Stream process did not finish in time, it may be stuck. Moving on with closing.")
            del self._faster_whisper_stream_process
        
        if self._queue is not None:
            self._xlog.debug("Deleting FasterWhisper Stream queue")
            del self._queue
        
        if self._support is not None:
            self._xlog.debug("Closing Support process from FasterWhisper Stream and deleting it")
            del self._support
        
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
    
