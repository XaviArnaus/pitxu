import logging

from pyxavi import Config, Dictionary, TerminalColor, full_stack
from pitxu.lib.speech_to_text.preprocess.preprocessor import Preprocessor
from pitxu.lib.speech_to_text.speech_to_text import SpeechToTextException
from pitxu.lib.support_process.support import Support
from pitxu.lib.support_process import support
from pitxu.lib.utils.xprocess_pool import XprocessPool
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction

import queue
from faster_whisper import WhisperModel
import os
import numpy as np
import difflib
import logging
import re

class FasterWhisperStreamProcess(Xprocess):
    """
    Class to transcribe audio chunks in a separate process, to avoid blocking the Main thread, after trying a separate thread in V3.
    """

    _model: WhisperModel = None
    _output_queue: queue.Queue = None
    _output_queue_sentinel: object = None
    _preprocessor: Preprocessor = None
    _shared_memory: SharedMemoryManager = None

    process_pool: XprocessPool = None

    on_transcription_finished_callback: callable = None

    is_active: bool = False
    language: str = "en"

    _beam_size = 5
    _overlap_size = 2000
    _chunks_window = 10
    _sleep_when_no_chunks = 0.1
    _use_low_confidence_threshold = False
    _low_confidence_threshold = -1

    # The last "n" samples of the previous chunk, to be used as context for the next chunk, to help the transcription model.
    _last_overlap = np.array([], dtype=np.float32)
    # The current (or final) state of the transcription
    _ongoing_transcription = ""
    # Store the last few words of the previous transcription
    _transcription_buffer = [] 

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

    def get_process_name(self) -> str:
        return "FasterWhisperStream"

    def initialize(self):
        self._xlog.info("Initializing FasterWhisperStream Worker")

        logging_parts = []

        language = self._xparams.get("language", "en-us")
        # I need to correct this Vosk language stupidity that is populated all around the code!!!
        self.language = language if language != "en-us" else "en"
        logging_parts.append(("Language", self.language))

        # Gathering the reference to the output queue, where to publish the results.
        self._output_queue = self.get_output_queue()
        self._output_queue_sentinel = self.get_sentinel_output_queue()
        
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

        # Forwarding the Support process queue to the Preprocessor via xparams,
        #   here just checking that it's there, for the log summary.
        logging_parts.append(("Support Class Queue is present", "Yes" \
                                if self._xparams.key_exists("support_class_queue") \
                                and self._xparams.get("support_class_queue") is not None \
                                else "No"))

        # COMMENTED: I can't pass the Support clas to the subprocess, as the Support classis already a subprocess.
        #   therfore, I can only send the queue for the Support class and then put the elements there.    
        # self.process_pool = XprocessPool(config=self._xconfig, params=self._xparams)
        # params = Dictionary({
        #     "process_pool": self.process_pool,
        #     "audio_parameters": self._xparams.get("audio_parameters"),
        # })
        # support = Support(config=self._xconfig, params=params)
        # params.set("support", support)
        params = Dictionary({
            "support_class_queue": self._xparams.get("support_class_queue"),
            "audio_parameters": self._xparams.get("audio_parameters"),
        })
        self._preprocessor = Preprocessor(config=self._xconfig, params=params)
        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory_flags()

        # Keeping track that Whisper is active
        self.is_active = True
        
    def finish(self):
        self._log_debug("Done finishing FasterWhisperStream Worker")

        if self._model is not None:
            self._xlog.debug("Deleting FasterWhisper Stream model")
            del self._model
        
        if self._output_queue is not None:
            self._xlog.debug("Deleting FasterWhisper Stream output queue")
            del self._output_queue
        
        if self._sentinel_output_queue is not None:
            self._xlog.debug("Deleting FasterWhisper Stream sentinel output queue")
            del self._sentinel_output_queue
        
        # Remember that FasterWhisper Stream is not active anymore
        self.is_active = False

        self._xlog.debug("Done finishing FasterWhisperStream Worker")
    
    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        
        if action == XprocAction.RESET_TRANSCRIPTION:
            self.reset_context()
        
        if action == XprocAction.TRANSCRIBE_CHUNK_WINDOW:
            if isinstance(param, list) and all(isinstance(chunk, bytes) for chunk in param):
                return self.process_chunks(param)
            else:
                raise ValueError("Invalid parameter for TRANSCRIBE_CHUNK_WINDOW action, expected a list of bytes (audio chunks).")
        
        if action == XprocAction.RETRIEVE_TRANSCRIPTION_RESULT:
            return self.get_transcription()
    
    def reset_context(self):
        self._last_overlap = np.array([], dtype=np.float32)
        self._ongoing_transcription = ""
        self._transcription_buffer = []
    
    def process_chunks(self, chunk_list: list[bytes]) -> str:
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
            # else:
            #     texts.append(segment.text)
            previous_word = ""
            previous_start = -1
            previous_end = -1
            previous_prob = -100
            for word in segment.words:
                # Sometimes the model goes crazy and repeats the exact same word un the segment.
                # So we can check for the same timestamps and probability and say it's a repetition and discard it.
                if word.word == previous_word and word.start == previous_start and word.end == previous_end and word.probability == previous_prob:
                    continue
                previous_word = word.word
                previous_start = word.start
                previous_end = word.end
                previous_prob = word.probability
                words_info.append((word.word, f"start: {round(word.start, 2)}, end: {round(word.end, 2)}, prob: {round(word.probability, 2)}"))
                text += word.word + " "
            texts.append(text.strip())
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
        # We get the final transcription and use the moment to clean it.
        final_transcription = self._clean_transcription(self._ongoing_transcription)

        # We put the transcription in the output queue, to be retrieved by the Main process.
        # if self._output_queue is not None and self._output_queue_sentinel is not None:
        if self._output_queue is not None:
            self._output_queue.put(final_transcription)
            # self._output_queue.put(self._output_queue_sentinel)
            self._log_debug("Final transcription put in the output queue with the sentinel.")
        else:
            self._xlog.error("🛑 Output queue or sentinel not available, cannot put the final transcription in the output queue.")
    
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

    
