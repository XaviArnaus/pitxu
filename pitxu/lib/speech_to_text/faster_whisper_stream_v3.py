from pyxavi import Dictionary, Config, TerminalColor, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.speech_to_text.preprocess.preprocessor import Preprocessor
from pitxu.lib.speech_to_text.speech_to_text import SpeechToTextException
from pitxu.lib.support_process.support import Support
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from definitions import SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY, SHARED_STT_BUSY

import threading
import queue
import time
from faster_whisper import WhisperModel
import os
import numpy as np
import difflib
import logging
import asyncio
import re

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

    _beam_size = 5
    _overlap_size = 2000
    _chunks_window = 10
    _sleep_when_no_chunks = 0.1
    _use_low_confidence_threshold = False
    _low_confidence_threshold = -1

    _last_overlap = np.array([], dtype=np.float32)
    _ongoing_transcription = ""
    _ongoing_chunk_window = []
    _worker_thread: threading.Thread = None
    _transcription_buffer = [] # Store the last few words of the previous transcription

    # List of human expressions that do not add any value, just noise.
    expressions_to_remove = ["urn", "um", "ye", "uh", "uhm", "ahm", "umm", "hmm", "mm", "uh", "ah", "mhm", "uhhh", "ahhh", "ummm", "hmmm", "mmhmm", "yeah,"]

    # List of punctuations to add to the words when searching for them in the transcription buffer,
    #   as they can be added by Faster Whisper and cause problems when merging.
    punctuations_to_add_to_words = [".", ",", "?", "!", "..."]

    # Avoid using the following words for the merging process, as they are too common and can cause more problems than benefits when merging,
    # Remember that they need to be all lowercase!
    words_to_remove_from_partial_transcription = ["i", "you", "he", "she", "it", "we", "they", "to", "and"] # This is for English, we can add more languages later if needed.

    # List of common hallucinated phrases. They usuallty come at the end of the transcription
    phrases_to_remove = [
        "thank you for watching",
        "thanks for watching",
        "subscribe for more",
    ]

    VERBOSE_DEBUG: bool = True

    THREAD_NAME = "Transcriptor"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(FasterWhisperStreamV3, self).init_pyxavi(config=config, params=params)

        self.initialize()
    
    def initialize(self):

        self._xlog.info("Initializing Faster Whisper Stream STT")
        logging_parts = []

        self.language = self._xparams.get("language", "en")
        if self.language == "en-us":
            # I need to correct this Vosk language stupidity that is populated all around the code!!!
            self.language = "en"
        logging_parts.append(("Language", self.language))

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
            model = self._xconfig.get("speech-to-text.faster_whisper_streaming.model." + self.language, None)
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
                device = str(self._xconfig.get("speech-to-text.faster_whisper_streaming.device", "cpu"))
                download_root = str(os.path.join(self._xconfig.get("storage.path"), self._xconfig.get("speech-to-text.faster_whisper_streaming.download_root", None)))
                compute_type = str(self._xconfig.get("speech-to-text.faster_whisper_streaming.compute_type", "int8"))
                beam_size = int(self._xconfig.get("speech-to-text.faster_whisper_streaming.beam_size", 5))
                overlap_size = int(self._xconfig.get("speech-to-text.faster_whisper_streaming.overlap_size", 2000))
                chunks_window = int(self._xconfig.get("speech-to-text.faster_whisper_streaming.chunks_window", 10))
                sleep_when_no_chunks = float(self._xconfig.get("speech-to-text.faster_whisper_streaming.sleep_when_no_chunks", 0.1))
                self._beam_size = beam_size
                self._overlap_size = overlap_size
                self._chunks_window = chunks_window
                self._sleep_when_no_chunks = sleep_when_no_chunks

                logging_parts.append(("Model from config", model))
                logging_parts.append(("Device for Faster Whisper", device))
                logging_parts.append(("Download root", download_root))
                logging_parts.append(("Compute type", compute_type))
                logging_parts.append(("Beam size", beam_size))
                logging_parts.append(("Overlap size", overlap_size))
                logging_parts.append(("Overlapping chunks duration at 16kHz (ms)", round(overlap_size / 16000 * 1000, 2)))
                logging_parts.append(("Chunks window", chunks_window))
                logging_parts.append(("Sleep when no chunks", sleep_when_no_chunks))
                logging_parts.append(("Faster Whisper logging level", logging.getLevelName(logging_level)))
                logging_parts.append(("HTTPX logging level", logging.getLevelName(httpx_logger_level)))
                logging_parts.append(("HTTPCore logging level", logging.getLevelName(httpcore_logger_level)))
                self.log_summary("Faster Whisper Stream Model Initialization", logging_parts)

                self._model = WhisperModel(model,
                                           device=device,
                                           download_root=download_root,
                                           compute_type=compute_type)
                # Warm up the model by running a dummy transcription, to avoid the long loading time of the first transcription.
                self.warm_up_model()
            else:
                raise SpeechToTextException(f"No model specified in config for language {self.language}, and mocking is disabled, cannot initialize Faster Whisper STT.")

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
        self._support = self._xparams.get("support")
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
        self._transcription_buffer = []
    
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
                    # Sleep for a short time to avoid busy waiting, and to give time to the other threads to add chunks to the queue.
                    time.sleep(self._sleep_when_no_chunks)
                    continue

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
                
                # At this point in time, if we have any ongoing transcription,
                #  means that the STT identified a speech and is processing.
                # If we're processing chunks but there is no transcription, it means that 
                #   the chunks do not contain a speech.
                if len(self._ongoing_transcription) > 0:
                    self.set_stt_busy()
                else:
                    self.unset_stt_busy()

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

        # Use the last "n" characters of the ongoing transcription as a prompt
        prompt_buffer_size_in_chars = 50
        if len(self._ongoing_transcription) > 0 and len(self._ongoing_transcription) < prompt_buffer_size_in_chars:
            prompt = self._ongoing_transcription
        elif len(self._ongoing_transcription) >= prompt_buffer_size_in_chars:
            prompt = self._ongoing_transcription[-prompt_buffer_size_in_chars:]
        else:
            prompt = ""

        self._log_debug(f"FasterWhisper Stream: Processing {len(chunk_list)} audio chunks with a total of {len(audio_to_process)} samples, with an overlap of {len(self._last_overlap)} samples from the previous chunk.")
        segments, _ = self._model.transcribe(
            audio_to_process,
            beam_size=self._beam_size,
            temperature=0.0,
            language=self.language,
            initial_prompt=prompt,
            word_timestamps=True
        )

        # What's the info that the segments bring? I'm interested in the timestamps
        seg_infos = []
        texts = []
        words_info = []
        for segment in segments:
            text = ""
            seg_infos.append((segment.text, f"start: {round(segment.start, 2)}, end: {round(segment.end, 2)}, prob: {round(segment.avg_logprob, 2)}"))
            if self._use_low_confidence_threshold and segment.avg_logprob < self._low_confidence_threshold:
                self._log_debug(f"FasterWhisper Stream: Segment with low confidence detected, avg_logprob: {segment.avg_logprob}, text: {segment.text}")
            else:
                texts.append(segment.text)
            previous_start = -1
            previous_end = -1
            previous_prob = -100
            for word in segment.words:
                # Sometimes the model goes crazy and repeats the exact same word un the segment.
                # So we can check for the same timestamps and probability and say it's a repetition and discard it.
                if word.start == previous_start and word.end == previous_end and word.probability == previous_prob:
                    continue
                previous_start = word.start
                previous_end = word.end
                previous_prob = word.probability
                words_info.append((word.word, f"start: {round(word.start, 2)}, end: {round(word.end, 2)}, prob: {round(word.probability, 2)}"))
        self.log_summary("Segments info", seg_infos, attend_verbose_debug_flag=True)
        self.log_summary("Words info", words_info, attend_verbose_debug_flag=True)

        # Some protection in case that low confidence segments are the only ones we have, to avoid hallucinations and wrong merging.
        if len(texts) == 0:
            self._log_debug("FasterWhisper Stream: No valid segments to process after transcription, returning empty result.")
            return ""

        # Update state
        current_text = " ".join(texts).strip()

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

        # Incomplete partial words are followed by an hyphen at the end of the word, at the end of the string. 
        #   If so, we need to remove the hyphen and the word completely.
        if partial_transcription.endswith("-"):
            partial_transcription = re.sub(r'\w-$', '', partial_transcription).strip()

        # Remove the uhm, ahm, etc. from the partial transcription, as they are not useful for us, and they can cause problems when merging with the ongoing transcription.
        for expr in self.expressions_to_remove:
            partial_transcription = partial_transcription.replace(expr.capitalize(), "")
            partial_transcription = partial_transcription.replace(expr, "")
        
        # After the previous we may end up with multiple spaces with dots, so we can remove them.
        partial_transcription = partial_transcription.replace(" .", ".").replace("  ", " ")

        # 2. Merging
        merged = ""

        self._log_debug(f"> Partial: {partial_transcription}")
        self._log_debug(f"> Transcription buffer before merging: {self._transcription_buffer}")
        self._log_debug(f"> Ongoing transcription before merging: {self._ongoing_transcription}")

        # --- Buffer and Wait Strategy --->

        # The words in the new partial transcription.
        new_words = partial_transcription.split()
        lowercased_new_words = [w.strip().lower() for w in new_words]

        # If we have a buffer, try to find the first complete word match
        if len(self._transcription_buffer) > 0 and len(new_words) > 0:
            found = False
            for i, word in enumerate(lowercased_new_words):
                # We want to skip searching for this word because it's too common and can cause more problems than benefits when merging, 
                # as it can be found in many places in the transcription buffer, and it doesn't add much value for the merging process.
                if word in self.words_to_remove_from_partial_transcription:
                    continue
                self._log_debug(f"* Searching for the word '{word}' in the transcription buffer")
                words_with_punctuation = [word + p for p in self.punctuations_to_add_to_words] + [word]
                lowercased_trascription_buffer = [w.strip().lower() for w in self._transcription_buffer]
                for word_with_punctuation in words_with_punctuation:
                    index_in_transcription_buffer = self.find_in_list_relative_from_behind(word_with_punctuation, lowercased_trascription_buffer)
                    if index_in_transcription_buffer is not None:
                        # Found a match! The new transcription starts from here.
                        found = True
                        # We discard everything before this word in the new chunk.
                        # Even we used the lowercased version for the search, we want to keep the original version, to avoid losing information.
                        self._log_debug(f"* Found the word '{word_with_punctuation}' in the transcription buffer at position {index_in_transcription_buffer}")
                        self._log_debug(f"* Merging '{new_words[i:]}' into '{self._ongoing_transcription.split()[:index_in_transcription_buffer]}'")
                        merged_words = self._ongoing_transcription.split()[:index_in_transcription_buffer] + new_words[i:]
                        merged = " ".join(merged_words)
                        self._transcription_buffer = merged_words[-5:]
                        # Once found, we don't keep on searching for the same word with any punctuation.
                        break
                # Why to keep on searching for the next words if we already found a match with the first one?
                if found:
                    break
            
            # If reaching this point there is no merged text, means that none of the new words matched with the buffer.
            # This means that the new transcription is completely different from the ongoing one, most likely because the transcription buffer
            #   was not cleaned in this transcription iteration, so we just append the new transcription to the ongoing one, without merging.
            if not merged:
                merged = self._ongoing_transcription + " " + partial_transcription
                self._transcription_buffer = merged.split()[-5:]
        # <---
        else:

            # Note: It feels like this is not needed:
            #   If we don't have a buffer, it means that we don't have any reference point to merge the new transcription,
            #       meaning, it's the first transcription we get, so we can just take it as it is. 
            #   If so, all this difflib logic in the ELSE is not needed, just take the new transcription as it is, 
            #       and save the last words in the buffer for the next iterations.

            # Use SequenceMatcher to find the overlap
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
            
            # Save some words for the next iteration.
            self._transcription_buffer = merged.split()[-5:]
        
        self._log_debug(f"< Transcription buffer after merging: {self._transcription_buffer}")
        self._log_debug(f"< Merged transcription after merging: {merged}")
        
        # 3. Cleaning.
        
        # If there are multiple dots in the merged transcription, replace them with a single dot.
        while ".." in merged:
            merged = merged.replace("..", ".")
        
        # If there are multiple space & comas in the merged transcription, just remove them.
        while " ," in merged:
            merged = merged.replace(" ,", "")

        self._ongoing_transcription = merged.strip()
        return self._ongoing_transcription
    
    def _clean_transcription(self, text: str) -> str:
        cleaned_text = text
        for phrase in self.phrases_to_remove:
            # Use case-insensitive matching and remove the phrase
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            cleaned_text = pattern.sub("", cleaned_text)

        return cleaned_text.strip()
    
    def get_transcription(self) -> str:
        """
        This method just retrieves the transcription done per chunks.
        """
        # Ensure that we're exhausting the leftover chunks in the window, if any, before getting the transcription.
        return self._clean_transcription(self._ongoing_transcription)
    
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
                
                # We finished processing all the chunks in the queue, now we dump and plot all audio data, and clean it for later.
                self._support.dump_and_plot_all()
                self._support.clear_accumulated_audio()

                # Join the chunks and transcribe them with FasterWhisper.
                #   Note: we don't want to join the chunks before preprocessing, because this could lead to memory issues if the user speaks for a long time, and also because the Preprocessor may do some operations that are better to do on smaller chunks (for example, VAD).
                segments, info = self._model.transcribe(
                    np.concatenate(audio_np).flatten().astype(np.float32) / 32768.0, 
                    beam_size=self._beam_size,
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
            self._worker_thread.join(timeout=2)
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
    
    def find_in_list_relative_from_behind(self, item, lst):
        """
        Find the first occurrence of an item in a list from the end, and return the index relative to the end.

        For example, if the list is ["hello", "world", "test", "hello"] and the item is "hello", it will return -1, 
        because the first occurrence of "hello" from the end is at index -1 (the last element). 
        If the item is "test", it will return -2, because the first occurrence of "test" from the end is at index -2. 
        If the item is not found, it will return None.
        """
        for i, element in enumerate(reversed(lst), 1):
            if element == item:
                return -i
        return None
    
    def warm_up_model(self):
        """
        Warms up the model by running a dummy inference with a silent audio chunk. This can help to reduce the latency of the first real inference.
        """
        self._log_debug("Warming up the Faster Whisper model with a silent audio chunk...")
        silent_chunk = self._generate_silent_audio_chunk(sample_rate=self._xparams.get("audio_parameters.stt_samplerate", 16000))
        self._model.transcribe(silent_chunk, beam_size=self._beam_size, temperature=0.0, language=self.language)
        self._log_debug("Faster Whisper model warmed up successfully.")

    def _generate_silent_audio_chunk(self, duration_seconds: float = 1.0,
                                 sample_rate: int = 16000,
                                 dtype: type = np.float32) -> np.ndarray:
        """
        Generates a silent audio chunk using numpy, compatible with faster-whisper.
        """
        num_samples = int(duration_seconds * sample_rate)
        silent_chunk = np.zeros(num_samples, dtype=dtype)
        return silent_chunk
    
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