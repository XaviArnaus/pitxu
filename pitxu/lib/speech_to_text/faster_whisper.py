from pyxavi import Dictionary, Config, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.speech_to_text.preprocess.preprocessor import Preprocessor
from pitxu.lib.speech_to_text.speech_to_text import SpeechToTextException
from pitxu.lib.support_process.support import Support
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from definitions import SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY

import queue
from faster_whisper import WhisperModel
import os
import numpy as np
import logging

class FasterWhisper(PyXavi):

    _model: WhisperModel = None
    _queue: queue.Queue = None
    _preprocessor: Preprocessor = None
    _support: Support = None
    _shared_memory: SharedMemoryManager = None

    is_active: bool = False
    language: str = "en"

    _overlap_size = 2000
    _chunks_window = 10
    _last_overlap = np.array([], dtype=np.float32)
    _ongoing_transcription = ""
    _ongoing_chunk_window = []

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(FasterWhisper, self).init_pyxavi(config=config, params=params)

        self.initialize()
    
    def initialize(self):

        self._xlog.info("Initializing Faster Whisper STT")
        logging_parts = []

        language = self._xparams.get("language", "en")
        if language == "en-us":
            # I need to correct this Vosk language stupidity that is populated all around the code!!!
            language = "en"
        logging_parts.append(("Language", language))

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
                self.log_summary("Faster Whisper Model Initialization", logging_parts)

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

        self.log_summary("Faster Whisper Initialization", logging_parts)
    
    def get_queue(self) -> queue.Queue:
        return self._queue
    
    def reset_context(self):
        self._last_overlap = np.array([], dtype=np.float32)
        self._ongoing_transcription = ""
        self._ongoing_chunk_window = []
    
    def recognize_chunks_from_queue(self) -> str:
        """
        This method is meant to be called while the user is speaking, to process the audio chunks in the queue with a sliding window approach.
        It processes only one chunk at a time, but it keeps an overlap of the last samples to provide context to the model.
        This is meant for the new Callback-based approach, where we want to process the audio data while the user is still speaking.
        """

        try:
            if self._xconfig.get("speech-to-text.mock", True):
                return input("Type your question: [\"exit\" to leave]: \n")
            elif self.is_active == False:
                self._xlog.warning("🟠 FasterWhisper is not active, cannot recognize audio")
            elif self.is_active and self._queue is not None:

                if self._queue.empty():
                    # No audio chunks in the queue to process
                    return ""

                partial_transcription = ""

                # Get all current chunks on the queue. It should be only one,
                #   but we could have the following cases:
                #   - The user is speaking very fast and the VAD is sending chunks faster than we can process them.
                #   - It is the start of the VAD detection, that VAD adds some previous chunks as a window before the detection.
                # self._log_debug(f"FasterWhisper: Processing audio chunks from the queue, current queue size: {self._queue.qsize()}")


                # First approach, process all the chunks in the queue, one by one, and concatenate the results.
                # ⚠️ Apparently the loop never ends. Could be that the queue is just getting new chunks faster than we can process them
                # while not self._queue.empty():
                #     data = self._queue.get()

                #     if data is None:
                #         self._log_debug("FasterWhisper: Received None data from the queue, skipping it.")
                #         continue
                #     else:
                #         partial_transcription += self.process_next_chunk(data)
                #         self._log_debug(f"FasterWhisper: Updated partial transcription: {partial_transcription}")
            
                # -----

                # Second approach, get the chunks from the queue so it gets empty ASAP, and process them in one shot.
                chunk_list_to_process = []
                while not self._queue.empty():
                    data = self._queue.get()

                    if data is None:
                        self._log_debug("FasterWhisper: Received None data from the queue, skipping it.")
                        continue
                    else:
                        if len(self._ongoing_chunk_window) > self._chunks_window:
                            self._log_debug(f"FasterWhisper: Ongoing chunk window exceeded the limit of {self._chunks_window} chunks. Processing.")
                            chunk_list_to_process.extend(self._ongoing_chunk_window.copy())
                            self._ongoing_chunk_window = []
                        self._ongoing_chunk_window.append(data)
                if len(chunk_list_to_process) > 0:
                    self._log_debug(f"FasterWhisper: Got {len(chunk_list_to_process)} audio chunks from the queue to process.")
                    partial_transcription = self._process_chunks(chunk_list_to_process)
                
                # -----

                # This is just partial, no need to react on this.
                return partial_transcription

        except queue.ShutDown as e:
            self.is_active = False
            raise SpeechToTextException("Queue Shutdown detected in FasterWhisper recognize(): " + str(e))
        except SpeechToTextException as ve:
            self.is_active = False
            # It's handled in Main, don't even log it here
            raise ve
        except KeyboardInterrupt:
            self._xlog.debug("Pressed Control + C while running FasterWhisper transcription.")
            self.is_active = False
            self.close()
        except BrokenPipeError as bpe:
            self.is_active = False
            raise SpeechToTextException("FasterWhisper BrokenPipeError: " + str(bpe))
        except Exception as e:
            self._xlog.error("🛑 Error during FasterWhisper recognition: " + str(e))
            self._xlog.error(full_stack())
            self.close()
            return None
    
    def _process_leftover_chunks(self) -> str:
        # Process the leftover chunks in the window, if any, with the context of the last overlap and the ongoing transcription.
        if len(self._ongoing_chunk_window) == 0:
            self._log_debug("FasterWhisper: No leftover audio chunks in the ongoing window to process.")
            return ""
        
        self._log_debug(f"FasterWhisper: Processing leftover {len(self._ongoing_chunk_window)} audio chunks from the ongoing window.")
        last_partial = self._process_chunks(self._ongoing_chunk_window)
        return last_partial
    
    def _process_chunks(self, chunk_list: list[bytes]) -> str:
        # Join together the chunks in the window and process them with the context of the last overlap and the ongoing transcription.
        self._log_debug(f"FasterWhisper: Processing {len(chunk_list)} audio chunks with the context of the last overlap and the ongoing transcription. Current ongoing transcription: '{self._ongoing_transcription}'")
        preprocessed_chunks = [self._preprocessor.preprocess_chunk(chunk, return_in_numpy=True) for chunk in chunk_list]
        preprocessed_chunks = list(filter(lambda x: x is not None and len(x) > 0, preprocessed_chunks))
        if len(preprocessed_chunks) == 0:
            self._log_debug("FasterWhisper: No valid audio chunks to process after preprocessing, returning empty result.")
            return ""
        preprocessed_chunks = np.concatenate(preprocessed_chunks).flatten().astype(np.float32) / 32768.0
        audio_to_process = np.concatenate([self._last_overlap, preprocessed_chunks]).flatten()

        self._log_debug(f"FasterWhisper: Processing {len(chunk_list)} audio chunks with a total of {len(audio_to_process)} samples, with an overlap of {len(self._last_overlap)} samples from the previous chunk.")
        segments, _ = self._model.transcribe(
            audio_to_process,
            beam_size=5,
            language=self.language,
            initial_prompt=self._ongoing_transcription
        )

        # Update state
        current_text = " ".join([s.text for s in segments]).strip()

        # Keep the last defined samples as overlap
        self._last_overlap = audio_to_process[-self._overlap_size:]
        self._ongoing_transcription = self._merge_partial_transcription(current_text)

        return current_text
    
    def _merge_partial_transcription(self, partial_transcription: str) -> str:

        # ---- Phase 0: Avoid doing work if no need for it, and initialize ----

        self._ongoing_transcription = self._ongoing_transcription.strip() if self._ongoing_transcription is not None else ""
        partial_transcription = partial_transcription.strip() if partial_transcription is not None else ""

        # No partial transcription, no further work to do.
        if partial_transcription == "":
            return self._ongoing_transcription

        # ---- Phase 1: Preprocessing the partial transcriptions to try to merge them better ----

        # Remove triple dots at the end, as they are added by Faster Whisper when it detects that the transcription is not finished,
        # but they are not useful for us, and they can cause problems when merging with the ongoing transcription.
        partial_transcription = partial_transcription.replace("...", "")

        # If the last character of the ongoing is not a punctuation, make the first character of the partial transcription lowercase, to try to merge them better.
        if len(self._ongoing_transcription) > 0 and self._ongoing_transcription[-1] not in [".", "!", "?"]:
             partial_transcription = partial_transcription[0].lower() + partial_transcription[1:]
        
        # Remove the uhm, ahm, etc. from the partial transcription, as they are not useful for us, and they can cause problems when merging with the ongoing transcription.
        expressions_to_remove = ["ye", "uh", "uhm", "ahm", "umm", "hmm", "mm", "uh", "ah", "mhm", "uhhh", "ahhh", "ummm", "hmmm", "mmhmm", "yeah,"]
        for expr in expressions_to_remove:
            partial_transcription = partial_transcription.replace(expr.capitalize(), "")
            partial_transcription = partial_transcription.replace(expr, "")
        
        # After the previous we may end up with multiple spaces with dots, so we can remove them.
        partial_transcription = partial_transcription.replace(" .", ".").replace("  ", " ")

        # In most of the cases, the partial transcription's last word is wrong or cut, so we can remove it to try to merge better with the ongoing transcription, that is more complete.
        if len(partial_transcription) > 0:
            partial_words = partial_transcription.split()
            if len(partial_words) > 1:
                partial_transcription = " ".join(partial_words[:-1])
        
        # In the partial transcription, after a comma the next word should be lowercase, and after a dot the next word should be uppercase, so we can fix this to try to merge better with the ongoing transcription.
        if len(partial_transcription) > 0:
            partial_words = partial_transcription.split()
            for i in range(1, len(partial_words)):
                if partial_words[i-1].endswith(","):
                    partial_words[i] = partial_words[i].lower()
                elif partial_words[i-1].endswith("."):
                    partial_words[i] = partial_words[i].capitalize()
            partial_transcription = " ".join(partial_words)
        
        # ---- Phase 2: Decide the merge itself ----

        merged_transcription = ""

        # The partial transcription is the same as the ongoing one, no need to merge, just return it.
        if self._ongoing_transcription.lower() == partial_transcription.lower():
            merged_transcription = self._ongoing_transcription

        # No ongoing transcription, just return the partial one.
        if self._ongoing_transcription == "":
            merged_transcription = partial_transcription

        # If the partial trascription is fully included in the ongoing transcription, we can just keep the ongoing transcription, it's more complete.
        if partial_transcription.lower() in self._ongoing_transcription.lower():
            merged_transcription = self._ongoing_transcription
        
        # If the last 2 words of the ongoing transcription are the same as the first 2 words of the partial transcription, we can merge them by removing the last 2 words of the ongoing transcription.
        ongoing_words = self._ongoing_transcription.lower().split()
        partial_words = partial_transcription.lower().split()
        if len(ongoing_words) > 1 and len(partial_words) > 1 and ongoing_words[-2:] == partial_words[:2]:
            merged = " ".join(ongoing_words[:-2]) + " " + " ".join(partial_words)
            merged_transcription = merged.strip()
        
        # If the last word of the ongoing transcription is the same as the first word of the partial transcription, we can merge them by removing the last word of the ongoing transcription.
        ongoing_words = self._ongoing_transcription.lower().split()
        partial_words = partial_transcription.lower().split()
        if len(ongoing_words) > 0 and len(partial_words) > 0 and ongoing_words[-1] == partial_words[0]:
            merged = " ".join(ongoing_words[:-1]) + " " + " ".join(partial_words)
            merged_transcription = merged.strip()
        
        # Still here? Just concatenate them, we couldn't find any common words to merge them better.
        merged = self._ongoing_transcription + " " + partial_transcription
        merged_transcription = merged.strip()

        # ---- Phase 3: Postprocessing the merged transcription to try to make it better ----

        # If the merged transcription has multiple spaces, replace them with a single space.
        merged_transcription = merged_transcription.replace("  ", " ")

        # In the merged transcription, after a comma the next word should be lowercase, and after a dot the next word should be uppercase, so we can fix this to try to merge better with the ongoing transcription.
        if len(merged_transcription) > 0:
            partial_words = merged_transcription.split()
            for i in range(1, len(partial_words)):
                if partial_words[i-1].endswith(","):
                    partial_words[i] = partial_words[i].lower()
                elif partial_words[i-1].endswith("."):
                    partial_words[i] = partial_words[i].capitalize()
            merged_transcription = " ".join(partial_words)
        
        # If there are multiple dots in the merged transcription, replace them with a single dot.
        while ".." in merged_transcription:
            merged_transcription = merged_transcription.replace("..", ".")
        
        # If we have a comma and a dot together with no space, we just leave the dot.
        merged_transcription = merged_transcription.replace(",.", ".").replace(".,", ".")
        
        # ---- Phase 4: Return the merged transcription and update the ongoing transcription with it -----
        return merged_transcription
    
    def get_transcription(self) -> str:
        """
        This method just retrieves the transcription done per chunks.
        """
        # Ensure that we're exhausting the leftover chunks in the window, if any, before getting the transcription.
        self._process_leftover_chunks()
        return self._ongoing_transcription
    
    # def process_next_chunk(self, data):
    #     # Preprocess
    #     preprocessed = self._preprocessor.preprocess_chunk(data, return_in_numpy=True)
    #     current_audio = preprocessed.astype(np.float32) / 32768.0

    #     # Sliding Window: Prepend overlap
    #     audio_to_process = [self._last_overlap, preprocessed]
    #     audio_to_process = np.concatenate(audio_to_process).flatten()

    #     self._log_debug(f"FasterWhisper: Processing new audio chunk with {len(current_audio)} samples, with an overlap of {len(self._last_overlap)} samples from the previous chunk, total {len(audio_to_process)} samples.")

    #     # Transcribe with context
    #     segments, _ = self._model.transcribe(
    #         audio_to_process,
    #         beam_size=5,
    #         language=self.language,
    #         initial_prompt=self._ongoing_transcription
    #     )

    #     # Update state
    #     current_text = " ".join([s.text for s in segments]).strip()
    #     dd(current_text)

    #     # Keep the last defined samples as overlap
    #     self._last_overlap = current_audio[-self._overlap_size:]
    #     self._ongoing_transcription = current_text

    #     return current_text
    
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

                self._log_debug(f"FasterWhisper: Processing all audio chunks [{self._queue.qsize()}] from the queue at once")

                audio_np = []

                # Process all the chunks in the queue until it's empty.
                while not self._queue.empty():

                    # Get the next chunk from the queue.
                    data = self._queue.get()

                    if data is None:
                        self._log_debug("FasterWhisper: Received None data from the queue, skipping it.")
                        continue

                    # Preprocess. Returns a numpy array in INT16 (PCM_16) format.
                    preprocessed_data = self._preprocessor.preprocess_chunk(data, return_in_numpy=True)

                    if preprocessed_data is None:
                        self._log_debug("FasterWhisper: Preprocessed data is None, skipping this chunk.")
                        continue

                    audio_np.append(preprocessed_data)
                
                self._log_debug(f"FasterWhisper: All audio chunks from the queue have been preprocessed, total {len(audio_np)} chunks. Transcribing them with FasterWhisper...")

                if len(audio_np) == 0:
                    self._log_debug("FasterWhisper: No audio chunks to process after preprocessing, returning empty result.")
                    return ""
                # Join the chunks and transcribe them with FasterWhisper.
                #   Note: we don't want to join the chunks before preprocessing, because this could lead to memory issues if the user speaks for a long time, and also because the Preprocessor may do some operations that are better to do on smaller chunks (for example, VAD).
                segments, info = self._model.transcribe(
                    np.concatenate(audio_np).flatten().astype(np.float32) / 32768.0, 
                    beam_size=5,
                    language=self.language)
                
                # The transcription actually is done per segment, it's a generator, so we could improve the code speed here.
                result = " ".join([segment.text for segment in segments]).strip()

                self._log_debug(f"FasterWhisper: Finished processing all audio chunks from the queue, final result: {result}")
                return result

        except queue.ShutDown as e:
            self.is_active = False
            raise SpeechToTextException("Queue Shutdown detected in FasterWhisper recognize(): " + str(e))
        except SpeechToTextException as ve:
            self.is_active = False
            # It's handled in Main, don't even log it here
            raise ve
        except KeyboardInterrupt:
            self._xlog.debug("Pressed Control + C while running FasterWhisper transcription.")
            self.is_active = False
            self.close()
        except BrokenPipeError as bpe:
            self.is_active = False
            raise SpeechToTextException("FasterWhisper BrokenPipeError: " + str(bpe))
        except Exception as e:
            self._xlog.error("🛑 Error during FasterWhisper recognition: " + str(e))
            self._xlog.error(full_stack())
            self.close()
            return None
    
    def close(self):
        self._xlog.info("Closing FasterWhisper STT")
        
        if self._model is not None:
            self._xlog.debug("Deleting FasterWhisper model")
            del self._model
        
        if self._queue is not None:
            self._xlog.debug("Deleting FasterWhisper queue")
            del self._queue
        
        if self._support is not None:
            self._xlog.debug("Closing Support process from FasterWhisper and deleting it")
            del self._support
        
        # Remember that FasterWhisper is not active anymore
        self.is_active = False

        self._xlog.info("FasterWhisper STT closed")