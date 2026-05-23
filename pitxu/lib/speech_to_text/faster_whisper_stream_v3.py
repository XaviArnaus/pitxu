from pyxavi import Dictionary, Config, TerminalColor, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.speech_to_text.preprocess.preprocessor import Preprocessor
from pitxu.lib.speech_to_text.speech_to_text import SpeechToTextException
from pitxu.lib.support_process.support import Support
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from definitions import SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY

import threading
import queue
from faster_whisper import WhisperModel
import os
import numpy as np
import difflib
import logging
import asyncio

class FasterWhisperStreamV3(PyXavi):
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

    _model: WhisperModel = None
    _queue: queue.Queue = None
    _preprocessor: Preprocessor = None
    _support: Support = None
    _shared_memory: SharedMemoryManager = None

    on_transcription_finished_callback: callable = None

    is_active: bool = False
    language: str = "en"

    _overlap_size = 2000
    _chunks_window = 10
    _last_overlap = np.array([], dtype=np.float32)
    _ongoing_transcription = ""
    _ongoing_chunk_window = []
    _worker_thread: threading.Thread = None

    VERBOSE_DEBUG: bool = True

    THREAD_NAME = "Transcriptor"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(FasterWhisperStreamV3, self).init_pyxavi(config=config, params=params)

        self.initialize()
    
    def initialize(self):

        self._xlog.info("Initializing Faster Whisper Stream STT")
        logging_parts = []

        language = self._xparams.get("language", "en")
        if language == "en-us":
            # I need to correct this Vosk language stupidity that is populated all around the code!!!
            language = "en"
        logging_parts.append(("Language", language))

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

        if self._xconfig.get("speech-to-text.mock", True):
            self._xlog.info("Mocking Speech-to-Text by Config. Model not loaded.")
        else:
            model = self._xconfig.get("speech-to-text.faster_whisper.model." + language, None)
            if model is not None:
                # Control the internal Faster Whisper logging
                logging_level = self._xconfig.get("libs_logger.faster_whisper.loglevel", logging.INFO)
                logging.getLogger("faster_whisper").setLevel(logging_level)
                # Control other support logging
                httpx_logger_level = self._xconfig.get("libs_logger.httpx.loglevel", logging.INFO)
                logging.getLogger("httpx").setLevel(httpx_logger_level)
                httpcore_logger_level = self._xconfig.get("libs_logger.httpcore.loglevel", logging.INFO)
                logging.getLogger("httpcore").setLevel(httpcore_logger_level)

                # I don't understand why device and download_root get read as tuples instead of strings.
                device = str(self._xconfig.get("speech-to-text.faster_whisper.device", "cpu"))
                download_root = str(os.path.join(self._xconfig.get("storage.path"), self._xconfig.get("speech-to-text.faster_whisper.download_root", None)))
                compute_type = str(self._xconfig.get("speech-to-text.faster_whisper.compute_type", "int8"))
                overlap_size = int(self._xconfig.get("speech-to-text.faster_whisper.overlap_size", 2000))
                chunks_window = int(self._xconfig.get("speech-to-text.faster_whisper.chunks_window", 10))
                self._overlap_size = overlap_size
                self._chunks_window = chunks_window

                logging_parts.append(("Model from config", model))
                logging_parts.append(("Device for Faster Whisper", device))
                logging_parts.append(("Download root", download_root))
                logging_parts.append(("Compute type", compute_type))
                logging_parts.append(("Overlap size", overlap_size))
                logging_parts.append(("Overlapping chunks duration at 16kHz (ms)", round(overlap_size / 16000 * 1000, 2)))
                logging_parts.append(("Chunks window", chunks_window))
                logging_parts.append(("Faster Whisper logging level", logging.getLevelName(logging_level)))
                logging_parts.append(("HTTPX logging level", logging.getLevelName(httpx_logger_level)))
                logging_parts.append(("HTTPCore logging level", logging.getLevelName(httpcore_logger_level)))
                self.log_summary("Faster Whisper Stream Model Initialization", logging_parts)

                self._model = WhisperModel(model,
                                           device=device,
                                           download_root=download_root,
                                           compute_type=compute_type)
                
            else:
                raise SpeechToTextException(f"No model specified in config for language {language}, and mocking is disabled, cannot initialize Faster Whisper STT.")

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
            logging_parts.append(("Support Class is present", "Yes" \
                                  if self._xparams.key_exists("support") \
                                    and self._xparams.get("support") is not None \
                                    and isinstance(self._xparams.get("support"), Support) \
                                  else "No"))

        self._queue = queue.Queue()
        self._preprocessor = Preprocessor(config=self._xconfig, params=self._xparams)
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
        self._last_overlap = np.array([], dtype=np.float32)
        self._ongoing_transcription = ""
        self._ongoing_chunk_window = []
    
    def _transcription_worker(self):
        """
        This is a worker that runs in a separate thread, that continuously processes the audio chunks in the queue 
        with a sliding window approach, while the user is still speaking.

        As we don't want to process chunk by chunk (they are too small for the Model), we need to accumulate the chunks in a window, 
        and process them together, with the context of the last overlap and the ongoing transcription.
        """

        # Initializations
        # partial_transcription = ""
        chunk_list_to_process = []
        
        while self.is_active:
            try:
                # Get all current chunks on the queue. It should be only one,
                #   but we could have the following cases:
                #   - The user is speaking very fast and the VAD is sending chunks faster than we can process them.
                #   - It is the start of the VAD detection, that VAD adds some previous chunks as a window before the detection.
                # self._log_debug(f"FasterWhisper Stream: Processing audio chunks from the queue, current queue size: {self._queue.qsize()}")

                # If the queue is empty, we just wait for the next chunk to arrive, without doing anything.
                if self._queue.empty():
                    continue

                # Get the next chunk from the queue.
                data = self._queue.get()

                if data is None:
                    self._log_debug("FasterWhisper Stream: Received None data from the queue, It should be the end of the stream.")

                    # Process the leftover chunks in the window, if any, with the context of the last overlap and the ongoing transcription.
                    _ = self._process_leftover_chunks()

                    # Clean anything LOCAL that would accumulate or trigger.
                    chunk_list_to_process = []
                    
                    # Trigger the callback to notify that the transcription is finished.
                    if self.on_transcription_finished_callback is not None:
                        self._log_debug("FasterWhisper Stream: Triggering on_transcription_finished_callback callback after processing the leftover chunks.")
                        # Be careful, it's part of asyncio loop.
                        asyncio.run_coroutine_threadsafe(self.on_transcription_finished_callback(), self.main_event_loop)
                else:
                    if len(self._ongoing_chunk_window) >= self._chunks_window:
                        self._log_debug(f"FasterWhisper Stream: Ongoing chunk window exceeded the limit of {self._chunks_window} chunks. Processing.")
                        chunk_list_to_process.extend(self._ongoing_chunk_window.copy())
                        self._ongoing_chunk_window = []
                    self._ongoing_chunk_window.append(data)

                if len(chunk_list_to_process) > 0:
                    self._log_debug(f"FasterWhisper Stream: Got {len(chunk_list_to_process)} audio chunks from the queue to process.")
                    _ = self._process_chunks(chunk_list_to_process)
                    chunk_list_to_process = []

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
    
    def _process_leftover_chunks(self) -> str:
        # Process the leftover chunks in the window, if any, with the context of the last overlap and the ongoing transcription.
        if len(self._ongoing_chunk_window) == 0:
            self._log_debug("FasterWhisper Stream: No leftover audio chunks in the ongoing window to process.")
            return ""
        
        self._log_debug(f"FasterWhisper Stream: Processing leftover {len(self._ongoing_chunk_window)} audio chunks from the ongoing window.")
        last_partial = self._process_chunks(self._ongoing_chunk_window)
        return last_partial
    
    def _process_chunks(self, chunk_list: list[bytes]) -> str:
        result = ""
        # Join together the chunks in the window and process them with the context of the last overlap and the ongoing transcription.
        self._log_debug(f"FasterWhisper Stream: Processing {len(chunk_list)} audio chunks with the context of the last overlap and the ongoing transcription.")
        preprocessed_chunks = [self._preprocessor.preprocess_chunk(chunk, return_in_numpy=True) for chunk in chunk_list]
        preprocessed_chunks = list(filter(lambda x: x is not None and len(x) > 0, preprocessed_chunks))
        if len(preprocessed_chunks) == 0:
            self._log_debug("FasterWhisper Stream: No valid audio chunks to process after preprocessing, returning empty result.")
            result = ""
        preprocessed_chunks = np.concatenate(preprocessed_chunks).flatten().astype(np.float32) / 32768.0
        audio_to_process = np.concatenate([self._last_overlap, preprocessed_chunks]).flatten()

        # Use the last 50 characters of the ongoing transcription as a prompt
        prompt = self._ongoing_transcription[-50:] if self._ongoing_transcription else ""

        self._log_debug(f"FasterWhisper Stream: Processing {len(chunk_list)} audio chunks with a total of {len(audio_to_process)} samples, with an overlap of {len(self._last_overlap)} samples from the previous chunk.")
        segments, _ = self._model.transcribe(
            audio_to_process,
            beam_size=2,
            language=self.language,
            initial_prompt=prompt
        )

        # Update state
        current_text = " ".join([s.text for s in segments]).strip()

        # Keep the last defined samples as overlap
        self._last_overlap = audio_to_process[-self._overlap_size:]
        self._ongoing_transcription = self._merge_partial_transcription(current_text)
        result = current_text

        self._xlog.debug(f"Current ongoing transcription: \n\n{TerminalColor.ORANGE}{self._ongoing_transcription}{TerminalColor.END}\n\n")
        return result
    
    def _merge_partial_transcription(self, partial_transcription: str) -> str:

        # 1. Clean the input
        partial_transcription = partial_transcription.strip()
        if not partial_transcription:
            return self._ongoing_transcription
        
        # Remove triple dots at the end, as they are added by Faster Whisper when it detects that the transcription is not finished,
        # but they are not useful for us, and they can cause problems when merging with the ongoing transcription.
        # This should help the difflib to find a better overlap
        partial_transcription = partial_transcription.replace("...", "")

        # If there is a hyphen at the end of a word followed by a space, it means that the word is cut, so we remove the hyphen.
        # This should help the difflib to find a better overlap
        partial_transcription = partial_transcription.replace("- ", " ")

        # Remove the uhm, ahm, etc. from the partial transcription, as they are not useful for us, and they can cause problems when merging with the ongoing transcription.
        expressions_to_remove = ["um", "ye", "uh", "uhm", "ahm", "umm", "hmm", "mm", "uh", "ah", "mhm", "uhhh", "ahhh", "ummm", "hmmm", "mmhmm", "yeah,"]
        for expr in expressions_to_remove:
            partial_transcription = partial_transcription.replace(expr.capitalize(), "")
            partial_transcription = partial_transcription.replace(expr, "")
        
        # After the previous we may end up with multiple spaces with dots, so we can remove them.
        partial_transcription = partial_transcription.replace(" .", ".").replace("  ", " ")

        # 2. Use SequenceMatcher to find the overlap
        # We look for the best match between the end of the ongoing transcription
        # and the beginning of the new partial transcription.
        matcher = difflib.SequenceMatcher(None, self._ongoing_transcription[-100:].lower(), partial_transcription[:100].lower())
        match = matcher.find_longest_match(0, len(self._ongoing_transcription[-100:]), 0, len(partial_transcription[:100]))

        if match.size > 10: # Threshold for a valid overlap
            # Merge by taking the ongoing part + the new part after the overlap
            merged = self._ongoing_transcription + partial_transcription[match.size:]
        else:
            # No significant overlap, just append
            merged = self._ongoing_transcription + " " + partial_transcription

        self._ongoing_transcription = merged.strip()
        return self._ongoing_transcription
    
    def get_transcription(self) -> str:
        """
        This method just retrieves the transcription done per chunks.
        """
        # Ensure that we're exhausting the leftover chunks in the window, if any, before getting the transcription.
        # self._process_leftover_chunks()
        return self._ongoing_transcription
    
    def recognize_all_queue_at_once(self) -> str:
        """
        Processes all chunks in the queue in one shot.
        It does NOT concatenate the chunks and process them all, because this could lead to memory issues if the user speaks for a long time.
            Instead, it processes each chunk one by one, and concatenates the results.
        This is meant for the new Callback-based approach, where we want to process the audio data at the end of the speech.
        """

        try:
            if self._xconfig.get("speech-to-text.mock", True):
                return input("Type your question: [\"exit\" to leave]: \n")
            elif self.is_active == False:
                raise SpeechToTextException("Whisper is not active, cannot recognize audio")
            elif self.is_active and self._queue is not None:

                result = None

                self._log_debug(f"FasterWhisper Stream: Processing all audio chunks [{self._queue.qsize()}] from the queue at once")

                audio_np = []

                # Process all the chunks in the queue until it's empty.
                while not self._queue.empty():

                    # Get the next chunk from the queue.
                    data = self._queue.get()

                    if data is None:
                        self._log_debug("FasterWhisper Stream: Received None data from the queue, skipping it.")
                        continue

                    # Preprocess. Returns a numpy array in INT16 (PCM_16) format.
                    preprocessed_data = self._preprocessor.preprocess_chunk(data, return_in_numpy=True)

                    if preprocessed_data is None:
                        self._log_debug("FasterWhisper Stream: Preprocessed data is None, skipping this chunk.")
                        continue

                    audio_np.append(preprocessed_data)
                
                self._log_debug(f"FasterWhisper Stream: All audio chunks from the queue have been preprocessed, total {len(audio_np)} chunks. Transcribing them with FasterWhisper...")

                if len(audio_np) == 0:
                    self._log_debug("FasterWhisper Stream: No audio chunks to process after preprocessing, returning empty result.")
                    return ""
                # Join the chunks and transcribe them with FasterWhisper.
                #   Note: we don't want to join the chunks before preprocessing, because this could lead to memory issues if the user speaks for a long time, and also because the Preprocessor may do some operations that are better to do on smaller chunks (for example, VAD).
                segments, info = self._model.transcribe(
                    np.concatenate(audio_np).flatten().astype(np.float32) / 32768.0, 
                    beam_size=5,
                    language=self.language)
                
                # The transcription actually is done per segment, it's a generator, so we could improve the code speed here.
                result = " ".join([segment.text for segment in segments]).strip()

                self._log_debug(f"FasterWhisper Stream: Finished processing all audio chunks from the queue, final result: {result}")
                return result

        except queue.ShutDown as e:
            self.is_active = False
            raise SpeechToTextException("Queue Shutdown detected in FasterWhisper recognize(): " + str(e))
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
            self._worker_thread.join(timeout=5)
            if self._worker_thread.is_alive():
                self._xlog.warning("FasterWhisper Stream worker thread did not finish in time, it may be stuck. Moving on with closing.")
            else:
                self._xlog.debug("FasterWhisper Stream worker thread finished successfully.")
        
        if self._model is not None:
            self._xlog.debug("Deleting FasterWhisper Stream model")
            del self._model
        
        if self._queue is not None:
            self._xlog.debug("Deleting FasterWhisper Stream queue")
            del self._queue
        
        if self._support is not None:
            self._xlog.debug("Closing Support process from FasterWhisper Stream and deleting it")
            del self._support
        
        # Remember that FasterWhisper Stream is not active anymore
        self.is_active = False

        self._xlog.info("FasterWhisper Stream STT closed")