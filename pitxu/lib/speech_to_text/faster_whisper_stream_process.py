import logging

from pyxavi import Config, Dictionary, TerminalColor, full_stack, dd
from pitxu.lib.speech_to_text.preprocess.preprocessor import Preprocessor
from pitxu.lib.speech_to_text.speech_to_text import SpeechToTextException
from pitxu.lib.core.xprocess_pool import XprocessPool
from pitxu.lib.core.shared_memory_manager import SharedMemoryManager

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction

import queue
from faster_whisper import WhisperModel
from faster_whisper.transcribe import Segment
import os
import numpy as np
import logging
import re

class FasterWhisperStreamProcess(Xprocess):
    """
    Class to transcribe audio chunks in a separate process, 
    to avoid blocking the Main thread, after trying a separate thread in a previous version.

    The idea is to send the audio chunks to this process, and then retrieve the transcription results from it, 
    in a streaming way, to be able to have mostly all transcription done by the time the user finishes talking,
    to improve user experience.

    We don't want to react on partials, that's why the transcription gets accumulated until requested.

    Improvements ideas:
    - Add a timeout for the transcription, to avoid getting stuck in case of problems with the model.
    - Some comment that we should not keep a "previous chunks window" because it conditions current chunk's outcome,
        so if the previous chunk has any issue, current chunk's transcription may be an hallucination. That could be the 
        source of our lack of accuracy in the RPi, as it is more prone to have issues due to lack of resources.
    - Limit the amount of threads / processes used by the model to avoid overloading the CPU, especially in the RPi.
        This can be done by setting the OMP_NUM_THREADS environment variable, 
        and also by controlling the number of threads used by the model itself if it has that option.
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
    _temperature = 0.2
    _sleep_when_no_chunks = 0.1
    _word_low_confidence_threshold = 0.1
    _hallucination_silence_threshold = 1.0
    _max_prompt_buffer_size_in_chars = 100
    _hallucination_low_confidence_segments_threshold = -0.8
    _hallucination_low_confidence_reset_threshold = -1
    _hallucination_low_confidence_segments_max_occurrences = 3

    # Identify and correct hallucinations: If we have "n" consecutive segments with low confidence,
    #   we can consider that the model is hallucinating and reset the context.
    _consecutive_low_confidence_segments = 0
    _should_disable_next_prompt = False # Flag to disable the prompt for the next transcribe call
    _last_segment_text_for_repetition = "" # Stores text of last segment for basic repetition check

    _last_committed_timestamp = 0.0
    _current_chunk_start_time = 0.0
    # _current_transcription_start_time = 0.0

    # The last "n" samples of the previous chunk, to be used as context for the next chunk, to help the transcription model.
    _last_overlap = np.array([], dtype=np.float32)
    # The current (or final) transcription buffer, as a list of dict with "text", "start" and "end" of the transcription, 
    #   to be able to correct previous partials with newer partials, and to have timestamps for the merging process.
    _ongoing_transcription:list[dict] = []
    _final_transcription = ""

    # List of human expressions that do not add any value, just noise.
    # Take these as default. The list gets overwritten by the config if there is a specific one for the language.
    expressions_to_remove: list = ["urn", "um", "ye", "uh", "uhm", "ahm", "umm", "hmm", "mm", "uh", "ah", "mhm", "uhhh", "ahhh", "ummm", "hmmm", "mmhmm", "yeah,"]

    # List of punctuations to add to the words when searching for them in the transcription buffer,
    #   as they can be added by Faster Whisper and cause problems when merging.
    # Take these as default. The list gets overwritten by the config if there is a specific one for the language.
    punctuations_to_add_to_words: list = [".", ",", "?", "!", "..."]

    # Avoid using the following words for the merging process, as they are too common and can cause more problems than benefits when merging,
    # Remember that they need to be all lowercase!
    # Take these as default. The list gets overwritten by the config if there is a specific one for the language.
    words_to_remove_from_partial_transcription: list = ["i", "you", "he", "she", "it", "we", "they", "to", "and"]

    # List of common hallucinated phrases. They usually come at the end of the transcription
    # Take these as default. The list gets overwritten by the config if there is a specific one for the language.
    phrases_to_remove: list = [
        "thank you for watching",
        "thanks for watching",
        "subscribe for more",
    ]

    _hot_words: list = []

    VERBOSE_DEBUG: bool = False

    def get_process_name(self) -> str:
        return "FWhisperStr"

    def initialize(self):
        self._xlog.info("Initializing FasterWhisperStream Worker")

        logging_parts = []

        self.language = self._xparams.get("language", "en")
        # ⚠️ I need to correct this Vosk language stupidity that is populated all around the code!!!
        # The issue was that Pitxu RPi still had the language set to 'en-us' instead of 'en'
        # language = self._xparams.get("language", "en")
        # self.language = language if language != "en-us" else "en"
        logging_parts.append(("Language", self.language))

        # Gathering the reference to the output queue, where to publish the results.
        self._output_queue = self.get_output_queue()
        self._output_queue_sentinel = self.get_sentinel_output_queue()

        # Fill the replacing strings from the config
        self.expressions_to_remove = self._xconfig.get("language.transcription_remove_expressions." + self._xparams.get("language"), self.expressions_to_remove)
        self.punctuations_to_add_to_words = self._xconfig.get("language.word_based_partial_transcriptions_punctuations." + self._xparams.get("language"), self.punctuations_to_add_to_words)
        self.phrases_to_remove = self._xconfig.get("language.transcription_hallucinations." + self._xparams.get("language"), self.phrases_to_remove)
        
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
            temperature = float(self._xconfig.get("speech-to-text.faster_whisper_streaming.temperature", 0.2))
            cpu_threads = int(self._xconfig.get("speech-to-text.faster_whisper_streaming.num_threads", 3))
            overlap_size = int(self._xconfig.get("speech-to-text.faster_whisper_streaming.overlap_size", 2000))
            chunks_window = int(self._xconfig.get("speech-to-text.faster_whisper_streaming.chunks_window", 10))
            sleep_when_no_chunks = float(self._xconfig.get("speech-to-text.faster_whisper_streaming.sleep_when_no_chunks", 0.1))
            word_low_confidence_threshold = float(self._xconfig.get("speech-to-text.faster_whisper_streaming.word_low_confidence_threshold", 0.1))
            max_prompt_buffer_size_in_chars = int(self._xconfig.get("speech-to-text.faster_whisper_streaming.max_prompt_buffer_size_in_chars", 100))
            hallucination_silence_threshold = float(self._xconfig.get("speech-to-text.faster_whisper_streaming.hallucination_silence_threshold", 1.0))
            hallucination_low_confidence_segments_threshold = float(self._xconfig.get("speech-to-text.faster_whisper_streaming.hallucination_low_confidence_segments_threshold", -0.8))
            hallucination_low_confidence_reset_threshold = float(self._xconfig.get("speech-to-text.faster_whisper_streaming.hallucination_low_confidence_reset_threshold", -1))
            hallucination_low_confidence_segments_max_occurrences = int(self._xconfig.get("speech-to-text.faster_whisper_streaming.hallucination_low_confidence_segments_max_occurrences", 3))

            self._beam_size = beam_size
            self._overlap_size = overlap_size
            self._chunks_window = chunks_window
            self._sleep_when_no_chunks = sleep_when_no_chunks
            self._hallucination_silence_threshold = hallucination_silence_threshold
            self._max_prompt_buffer_size_in_chars = max_prompt_buffer_size_in_chars
            self._temperature = temperature
            self._word_low_confidence_threshold = word_low_confidence_threshold
            self._hallucination_low_confidence_segments_threshold = hallucination_low_confidence_segments_threshold
            self._hallucination_low_confidence_reset_threshold = hallucination_low_confidence_reset_threshold
            self._hallucination_low_confidence_segments_max_occurrences = hallucination_low_confidence_segments_max_occurrences
            self._hot_words = self._load_hot_words()

            logging_parts.append(("Model from config", model))
            logging_parts.append(("Device for Faster Whisper", device))
            logging_parts.append(("Download root", download_root))
            logging_parts.append(("Compute type", compute_type))
            logging_parts.append(("Beam size", beam_size))
            logging_parts.append(("Temperature", temperature))
            logging_parts.append(("CPU threads", cpu_threads))
            logging_parts.append(("Overlap size", overlap_size))
            logging_parts.append(("Overlapping chunks duration at 16kHz (ms)", round(overlap_size / 16000 * 1000, 2)))
            logging_parts.append(("Chunks window", chunks_window))
            logging_parts.append(("Sleep when no chunks", sleep_when_no_chunks))
            logging_parts.append(("Word low confidence threshold", word_low_confidence_threshold))
            logging_parts.append(("Hallucination silence threshold", hallucination_silence_threshold))
            logging_parts.append(("Hallucination low confidence segments threshold", hallucination_low_confidence_segments_threshold))
            logging_parts.append(("Hallucination low confidence reset threshold", hallucination_low_confidence_reset_threshold))
            logging_parts.append(("Hallucination low confidence segments max occurrences", hallucination_low_confidence_segments_max_occurrences))
            logging_parts.append(("Max prompt buffer size in chars", max_prompt_buffer_size_in_chars))
            logging_parts.append(("Faster Whisper logging level", logging.getLevelName(logging_level)))
            logging_parts.append(("HTTPX logging level", logging.getLevelName(httpx_logger_level)))
            logging_parts.append(("HTTPCore logging level", logging.getLevelName(httpcore_logger_level)))
            logging_parts.append(("Hot words count", len(self._hot_words)))
            self.log_summary("Faster Whisper Stream Model Initialization", logging_parts)

            self._model = WhisperModel(model,
                                        device=device,
                                        download_root=download_root,
                                        compute_type=compute_type,
                                        cpu_threads=cpu_threads,
                                        )
            # Warm up the model by running a dummy transcription, to avoid the long loading time of the first transcription.
            self.warm_up_model()
        else:
            raise SpeechToTextException(f"No model specified in config for language {self.language}, and mocking is disabled, cannot initialize Faster Whisper STT.")

        # I can't pass the Support clas to the subprocess, as the Support class has already a subprocess.
        #   therfore, I can only send the queue for the Support class and then put the elements there.  
        #   Here I'm just checking that the queue is there, for the log summary.
        logging_parts.append(("Support Class Queue is present", "Yes" \
                                if self._xparams.key_exists("support_class_queue") \
                                and self._xparams.get("support_class_queue") is not None \
                                else "No"))  
        logging_parts.append(("Silence Input Queue is present", "Yes" \
                                if self._xparams.key_exists("silence_input_queue") \
                                and self._xparams.get("silence_input_queue") is not None \
                                else "No"))  
        params = Dictionary({
            "support_class_queue": self._xparams.get("support_class_queue"),
            "audio_parameters": self._xparams.get("audio_parameters"),
            "silence_input_queue": self._xparams.get("silence_input_queue")
        })
        self._preprocessor = Preprocessor(config=self._xconfig, params=params)
        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory_flags()

        # Keeping track that Whisper is active
        self.is_active = True

        self.log_summary("FasterWhisperStream Worker Initialization", logging_parts)
    
    def _load_hot_words(self) -> list[str]:
        """
        Loads the hot words from the config and adds them to the model.
        """
        hot_words = []
        hot_words = self._xconfig.get("speech-to-text.faster_whisper_streaming.hot_words." + self.language, [])
        # COMMENTED: Feels like silences and so on are transcribed as hotwords.
        # hot_words.extend([self._xconfig.get("chatbot.name")] + self._xconfig.get("chatbot.name_variations", []))
        return hot_words
        
    def finish(self):
        self._log_debug("Finishing FasterWhisperStream Worker")

        # Remember that FasterWhisper Stream is not active anymore
        self.is_active = False

        if self._preprocessor is not None:
            self._xlog.debug("Deleting STT preprocessor")
            self._preprocessor.close()
            del self._preprocessor

        if self._output_queue is not None:
            self._xlog.debug("Deleting FasterWhisper Stream output queue")
            self._output_queue.join()
            del self._output_queue
        
        if self._sentinel_output_queue is not None:
            self._xlog.debug("Deleting FasterWhisper Stream sentinel output queue")
            del self._sentinel_output_queue

        if self._model is not None:
            self._xlog.debug("Deleting FasterWhisper Stream model")
            del self._model
        
        # COMMENTED: Shared memory should only be closed from XProcessPool.close() (so, by the Interaction.close()),
        #   otherwise the memory is tried to be closed several times.
        # if self._shared_memory is not None:
        #     self._xlog.debug("Closing Shared Memory from FasterWhisper Stream")
        #     self._shared_memory.close()
        #     del self._shared_memory

        
        self._xlog.debug("Done finishing FasterWhisperStream Worker")
    
    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        
        if action == XprocAction.RESET_TRANSCRIPTION:
            self.reset_context()
        
        if action == XprocAction.TRANSCRIBE_CHUNK_WINDOW:
            if isinstance(param, list) and all(isinstance(chunk, bytes) for chunk in param):
                # ⚠️ What is this return? If it puts partials into the queue... whouldn't be this
                #   the repetitions that I see? I don't expect elements in the queue but the very final one!
                # Still not sure whe this return, but the repetitions came from bad timestamp calculation,
                #   forghetting the overlap extra duration.
                # REMOVED THE RETURN.
                self.process_chunks(param)
            else:
                raise ValueError("Invalid parameter for TRANSCRIBE_CHUNK_WINDOW action, expected a list of bytes (audio chunks).")
        
        if action == XprocAction.RETRIEVE_TRANSCRIPTION_RESULT:
            return self.get_transcription()
    
    def reset_context(self):
        self._last_overlap = np.array([], dtype=np.float32)
        self._ongoing_transcription = []
        self._final_transcription = ""
        self._last_committed_timestamp = 0.0
        self._current_chunk_start_time = 0.0
        self._current_transcription_start_time = 0.0
        self._should_disable_next_prompt = False
    
    def process_chunks(self, chunk_list: list[bytes]) -> str:
        result = ""

        # 1. Preprocessing
        self._log_debug(f"FasterWhisper Stream: Processing {len(chunk_list)} audio chunks with the context of the last overlap and the ongoing transcription.")
        preprocessed_chunks = [self._preprocessor.preprocess_chunk(chunk, return_in_numpy=True) for chunk in chunk_list]
        preprocessed_chunks = list(filter(lambda x: x is not None and len(x) > 0, preprocessed_chunks))

        if len(preprocessed_chunks) == 0:
            # No chunks, no work.
            self._log_debug("FasterWhisper Stream: No valid audio chunks to process after preprocessing, returning empty result.")
            result = ""

        else:
            # 2. Prepare audio for transcription
            preprocessed_chunks = np.concatenate(preprocessed_chunks).flatten().astype(np.float32) / 32768.0
            audio_to_process = np.concatenate([self._last_overlap, preprocessed_chunks]).flatten()

            # Calculate chunk duration for the offset
            chunk_duration = (len(preprocessed_chunks) / self._xconfig.get("speech-to-text.target_samplerate", 16000)) \
                                if len(preprocessed_chunks) > 0 else 0.0

            # 3. Prepare prompt for the thranscription
            condition_on_previous_text = self._should_disable_next_prompt
            if self._should_disable_next_prompt:
                # The analysis of the confidence after transcription tells us that the model is hallucinating,
                # so we disable the prompt for the next transcription call, to avoid conditioning it with a wrong prompt, 
                # and we reset the flag.
                # The boolean flag is set in the _validate_last_segment_confidence_to_avoid_hallucination() method.
                prompt = ""
                self._should_disable_next_prompt = False
            else:
                # Prompt logic: Use the last "n" characters of the ongoing transcription as a prompt
                if len(self._ongoing_transcription) > 0:
                    text_in_ongoing_transcription = " ".join([t["word"] for t in self._ongoing_transcription])
                    if len(text_in_ongoing_transcription) < self._max_prompt_buffer_size_in_chars:
                        prompt = text_in_ongoing_transcription
                    elif len(text_in_ongoing_transcription) >= self._max_prompt_buffer_size_in_chars:
                        prompt = text_in_ongoing_transcription[-self._max_prompt_buffer_size_in_chars:]
                else:
                    prompt = ""

            # 4. Transcription
            self._log_debug(f"FasterWhisper Stream: Processing {len(chunk_list)} audio chunks with a total of {len(audio_to_process)} samples, with an overlap of {len(self._last_overlap)} samples from the previous chunk.")
            segments, _ = self._model.transcribe(
                audio_to_process,
                beam_size=self._beam_size,
                temperature=self._temperature,
                language=self.language,
                initial_prompt=prompt,
                word_timestamps=True,
                # Values over 1.0 reduce repetitions. Too high values can cause missing words, so we need to find a good balance.
                # It was 1.5, and some words were missing. Lowering down to 1.2.
                repetition_penalty=1.2,
                chunk_length=audio_to_process.shape[0], # We process the whole chunk with the context, as it is not splitted in smaller chunks for the transcription, to avoid losing context and to let the model decide how to split it.
                condition_on_previous_text=condition_on_previous_text,
                hallucination_silence_threshold=self._hallucination_silence_threshold,
                hotwords=" ".join(self._hot_words) if len(self._hot_words) > 0 else None
            )

            # The transcription is returned as a generator. Get the segments themselves.
            segments = list(segments)

            # Trying to identify hallucinations by looking at the confidence of the segments,
            # and if we have "n" consecutive low confidence segments, we consider that the model is hallucinating 
            # and we reset the context.
            self._validate_last_segment_confidence_to_avoid_hallucination(segments)

            # 4. Timestamp-based Merging
            seg_infos = []  # This is just for logging.
            words_info = [] # This is just for logging.
            low_probability_words = [] # This is just for logging, to keep track of the words that are below the confidence threshold.
            # new_words = []  # Here will be the commited words after comparing via timestamp.
            new_transcribed_words = []
            # The offsets of the word are from the segment, not the chunk.
            # we need to add the segment offset to the word time.
            current_segment_starting_time = self._last_committed_timestamp
            current_segment_ending_time = self._last_committed_timestamp
            # We need a correction factor related to the overlap that we add in front. 
            # Otherwise, the merger thinks that the firs word starts at 0s, but in reality it starts from -overlap_duration.
            # Also, the overlap size may be smaller than the chunk duration, for example in very small chunks.
            # COMMENTED: The merging is eating some words. Commented for now to see if it improves.
            # real_overlap_duration = min(self._overlap_size / self._xconfig.get("speech-to-text.target_samplerate", 16000), chunk_duration)
            # current_segment_starting_time = current_segment_starting_time - real_overlap_duration

            for segment in segments:

                current_segment_starting_time = current_segment_starting_time + segment.start
                current_segment_ending_time = current_segment_ending_time + segment.end
                seg_infos.append((segment.text, f"start: {round(segment.start, 2)} ({round(current_segment_starting_time, 2)}), end: {round(segment.end, 2)} ({round(current_segment_ending_time, 2)}), prob: {round(segment.avg_logprob, 2)}"))

                # Now, every word in this segment.
                for word in segment.words:

                    # Just discard very low confidence words
                    if word.probability < self._word_low_confidence_threshold:
                        low_probability_words.append((word.word, word.probability))
                        continue

                    # Still here? count on it.
                    # Prepare the real offsets for the words.
                    word_real_start = current_segment_starting_time + word.start
                    word_real_end = current_segment_starting_time + word.end
                    words_info.append((word.word, f"start: {round(word.start, 2)} ({round(word_real_start, 2)}), end: {round(word.end, 2)} ({round(word_real_end, 2)}), prob: {round(word.probability, 2)}"))

                    # Keep track of the new transcribed words, to be able to use them in the merging process,
                    # as they may be more accurate than the previous ongoing transcription.
                    new_transcribed_words.append({
                        'word': self._clean_word(word.word),
                        'start': word_real_start,
                        'end': word_real_end,
                        'confidence': word.probability
                    })

            # Just a logging to see the outcome of the analysis.
            if seg_infos:
                self.log_summary("Segments info", seg_infos, attend_verbose_debug_flag=True)
            if words_info:
                self.log_summary("Words info", words_info, attend_verbose_debug_flag=True)
            if low_probability_words:
                self.log_summary(f"Low confidence words ({self._word_low_confidence_threshold})", low_probability_words, attend_verbose_debug_flag=True)

            # 5. Update state
            self._ongoing_transcription = self._merge_and_correct_transcription(
                self._ongoing_transcription,
                new_transcribed_words
            )

            ongoing_transcription_text = " ".join([w['word'] for w in self._ongoing_transcription])
            self._xlog.debug(f"✏️ Current ongoing transcription: \n\n{TerminalColor.ORANGE}{ongoing_transcription_text}{TerminalColor.END}\n")

            # 6. Commit logic: Only emit words that are older than the stability threshold
            #    (e.g., 2 seconds old relative to the latest processed audio)
            stability_threshold = 2.0
            self._last_committed_timestamp = word_real_end if len(new_transcribed_words) > 0 else self._last_committed_timestamp

            committed_words = [w for w in self._ongoing_transcription if w['end'] < (self._last_committed_timestamp - stability_threshold)]
            self._ongoing_transcription = [w for w in self._ongoing_transcription if w['end'] >= (self._last_committed_timestamp - stability_threshold)]

            if committed_words:
                # Emit the committed words (e.g., put them in the output queue)
                self._final_transcription += " " + " ".join([w['word'] for w in committed_words])
                result = self._final_transcription
            
            # At this point, this is what we have, even it's going to be corrected on-the-go.
            # Emit it, so the caller can see a partial.
            self._emit_transcription(partial_transcription=self._final_transcription.strip() + " " + " ".join([w['word'] for w in self._ongoing_transcription]))

            # Keep the last defined samples as overlap
            self._last_overlap = audio_to_process[-self._overlap_size:]

        self._xlog.debug(f"✏️ Current committed transcription: \n\n{TerminalColor.ORANGE_BRIGHT}{result}{TerminalColor.END}\n")
        return result
    
    def _emit_transcription(self, final_transcription: str = None, partial_transcription: str = None):
        # It's a tuple: (partial, final)
        queue_item = (partial_transcription.strip() if partial_transcription is not None else None,
            final_transcription.strip() if final_transcription is not None else None
        )
        self._output_queue.put(queue_item)

    def _merge_and_correct_transcription(self, current_buffer: list, new_words: list) -> list:
        """
        Merges new words into the buffer. If a new word overlaps with the end of the
        current buffer, it replaces the old word (assuming the new one is a correction).
        """
        if not new_words:
            return current_buffer

        # 1. Find the cut-off point: where the new words start
        first_new_word_start = new_words[0]['start']

        # 2. Keep words from the buffer that end BEFORE the new words start
        #    These are "stable" and won't be corrected.
        stable_words = [w for w in current_buffer if w['end'] <= first_new_word_start]

        # 3. The new words effectively replace everything in the buffer
        #    that started after the cut-off point.
        return stable_words + new_words
    
    def _clean_word(self, word: str) -> str:
        """
        Cleans a single word by removing filler expressions and punctuation.
        """
        cleaned_word = word.strip()

        # Remove filler expressions
        for expr in self.expressions_to_remove:
            if cleaned_word.lower() == expr.lower():
                return ""

        # Remove trailing hyphens (common in partial words)
        if cleaned_word.endswith("-"):
            cleaned_word = re.sub(r'\w-$', '', cleaned_word).strip()

        return cleaned_word
    
    def _clean_transcription(self, text: str) -> str:
        cleaned_text = text
        for phrase in self.phrases_to_remove:
            # Use case-insensitive matching and remove the phrase
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            cleaned_text = pattern.sub("", cleaned_text)
        
        # Remove multiple consecutive dots that can appear at the end of the transcription, 
        # as they do not add value and can cause problems in the post-processing.
        cleaned_text = re.sub(r'\.{2,}', ' ', cleaned_text)
        # Remove all punctuations.
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        # Remove underscores
        cleaned_text = cleaned_text.replace("_", " ")
        # If the last 2 sentences already appear in the transcription, 
        # remove them as the model hallucinated
        # COMMENTED: Feels like its not needed anymore, 
        #   as the model does not hallucinate the end of the transcription that much
        # cleaned_text = re.sub(r'([^.]*\.\s*){1,2}$', r'\1', cleaned_text).strip()

        return cleaned_text.strip()

    def _validate_last_segment_confidence_to_avoid_hallucination(self, segments: list[Segment]) -> bool:
        """
        Analyses the last segment's confidence, calculates an average for the batch,
        and if it detects a low confidence segment, it sets a flag to disable the prompt for the next transcription call, 
        to avoid conditioning it with a wrong prompt, which can lead to a cascade of hallucinations. 
        It also has a reset mechanism that if we have "n" consecutive low confidence segments, 
        we consider that the model is hallucinating and we reset the context.
        """
        if segments:
            last_segment = segments[-1]
            segment_confidences = [s.avg_logprob for s in segments]
            avg_batch_confidence = np.mean(segment_confidences) if segment_confidences else 0.0

            is_hallucinating = False
            if last_segment.avg_logprob < self._hallucination_low_confidence_segments_threshold:
                is_hallucinating = True

            if len(last_segment.text.strip()) > 0 and \
            len(last_segment.text.strip()) < 6 and \
            last_segment.text.strip().lower() == self._last_segment_text_for_repetition.lower() and \
            last_segment.avg_logprob < (self._hallucination_low_confidence_segments_threshold * 1.5):
                is_hallucinating = True

            if is_hallucinating:
                self._should_disable_next_prompt = True

            self._last_segment_text_for_repetition = last_segment.text.strip()

            # --- 2. Reset Mechanism for Consecutive Low Confidence ---
            if avg_batch_confidence < self._hallucination_low_confidence_reset_threshold:
                self._consecutive_low_confidence_segments += 1
            else:
                self._consecutive_low_confidence_segments = 0

            if self._consecutive_low_confidence_segments >= self._hallucination_low_confidence_segments_max_occurrences:
                self._xlog.warning(f"✏️ Detected {self._consecutive_low_confidence_segments} consecutive low confidence segments with avg batch confidence {avg_batch_confidence:.2f}. Resetting transcription context to avoid hallucinations.")
                # We specifically don't reset the final transcription, as it is already committed and we want to keep it,
                # but we reset the ongoing transcription and the overlap, which are the context for the next transcriptions, 
                # to avoid that the hallucination cascade continues.
                self._ongoing_transcription = [] # Reset to empty list for the ongoing transcription
                self._last_overlap = np.array([], dtype=np.float32) # Reset to empty numpy array
                self._consecutive_low_confidence_segments = 0
                self._should_disable_next_prompt = True

    
    def get_transcription(self) -> str:
        """
        This method just retrieves the transcription done per chunks.
        """

        # We may still have some ongoing transcription that is not yet committed, so we add them to the final transcription,
        # As we don't expect more partials to correct it.
        leftover_transcription = " ".join([w['word'] for w in self._ongoing_transcription])
        if leftover_transcription:
            self._final_transcription += " " + leftover_transcription if self._final_transcription else leftover_transcription

        # We get the final transcription and use the moment to clean it.
        final_transcription = self._clean_transcription(self._final_transcription)

        self._xlog.debug(f"✏️ Final transcription: \n\n{TerminalColor.RED}{final_transcription}{TerminalColor.END}\n")

        # We put the transcription in the output queue, to be retrieved by the Main process.
        if self._output_queue is not None:
            self._emit_transcription(final_transcription=final_transcription)
            # self._output_queue.put(self._output_queue_sentinel)
            self._log_debug("Final transcription put in the output queue.")
            # Reset the context to avoid issues if the start does not trigger well
            self.reset_context()
        else:
            self._xlog.error("🛑 Output queue not available, cannot put the final transcription in the output queue.")
    
    def warm_up_model(self):
        """
        Warms up the model by running a dummy inference with a silent audio chunk. This can help to reduce the latency of the first real inference.
        """
        self._log_debug("Warming up the Faster Whisper model with a silent audio chunk...")
        silent_chunk = self._generate_silent_audio_chunk(duration_seconds=2.0, sample_rate=self._xparams.get("audio_parameters.stt_samplerate", 16000))
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

# ISSUE 1
# The with or the noise at the end of the trancription makes him allucinate.
#   1. I implemented a silence removeal that appeared strict when wront chunk merging was implemented
#   2. I deactivated it, indoors shown not needed, and produced bugs (maybe wrong overlap timestamp calculation)
#   3. Tested outdoors again, shows that wind/noise creates hallucinations at the end of the transcription

# 2026-06-04 18:25:38,232 [FWhisperStr MainThread            ] DEBUG    pitxu        Xprocess [FWhisperStr] run() received a [RESET_TRANSCRIPTION]
# 2026-06-04 18:25:38,262 [MainProcess TranscriptorManager   ] DEBUG    pitxu        👁️‍🗨️ Transitioning from START_CONTEXT to ONGOING_PROCESS_CHUNK
# 2026-06-04 18:25:39,164 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:39,182 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: 
# 2026-06-04 18:25:40,164 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:40,175 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: 
# 2026-06-04 18:25:41,191 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:41,197 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: 
# 2026-06-04 18:25:41,289 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Ongoing chunk window exceeded the limit of 150 chunks. Processing.
# 2026-06-04 18:25:41,302 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Got 150 audio chunks from the queue to process.
# 2026-06-04 18:25:41,308 [MainProcess TranscriptorManager   ] DEBUG    pitxu        Sending chunks window to be transcribed into the process
# 2026-06-04 18:25:41,321 [FWhisperStr MainThread            ] DEBUG    pitxu        Xprocess [FWhisperStr] run() received a [TRANSCRIBE_CHUNK_WINDOW: <class 'list'>]
# 2026-06-04 18:25:41,322 [FWhisperStr MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 150 audio chunks with the context of the last overlap and the ongoing transcription.
# 2026-06-04 18:25:41,410 [FWhisperStr MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 150 audio chunks with a total of 51201 samples, with an overlap of 0 samples from the previous chunk.
# 2026-06-04 18:25:41,411 [FWhisperStr MainThread            ] INFO     faster_whisper Processing audio with duration 00:03.200
# 2026-06-04 18:25:42,179 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:42,190 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: 
# 2026-06-04 18:25:42,830 [FWhisperStr MainThread            ] DEBUG    pitxu        -------------------------------------------------------------
# 2026-06-04 18:25:42,831 [FWhisperStr MainThread            ] DEBUG    pitxu        |                       Segments info                       |
# 2026-06-04 18:25:42,831 [FWhisperStr MainThread            ] DEBUG    pitxu        -------------------------------------------------------------
# 2026-06-04 18:25:42,831 [FWhisperStr MainThread            ] DEBUG    pitxu        |  Goodbye: start: 0.0 (0.0), end: 0.86 (0.86), prob: -0.95 |
# 2026-06-04 18:25:42,832 [FWhisperStr MainThread            ] DEBUG    pitxu        -------------------------------------------------------------
# 2026-06-04 18:25:42,832 [FWhisperStr MainThread            ] DEBUG    pitxu        ------------------------------------------------------------
# 2026-06-04 18:25:42,832 [FWhisperStr MainThread            ] DEBUG    pitxu        |                        Words info                        |
# 2026-06-04 18:25:42,833 [FWhisperStr MainThread            ] DEBUG    pitxu        ------------------------------------------------------------
# 2026-06-04 18:25:42,833 [FWhisperStr MainThread            ] DEBUG    pitxu        |  Goodbye: start: 0.0 (0.0), end: 0.86 (0.86), prob: 0.56 |
# 2026-06-04 18:25:42,833 [FWhisperStr MainThread            ] DEBUG    pitxu        ------------------------------------------------------------
# 2026-06-04 18:25:42,834 [FWhisperStr MainThread            ] DEBUG    pitxu        ✏️ Current ongoing transcription: 

# Goodbye

# 2026-06-04 18:25:42,834 [FWhisperStr MainThread            ] DEBUG    pitxu        ✏️ Current committed transcription: 



# 2026-06-04 18:25:43,150 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:43,163 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye
# 2026-06-04 18:25:44,152 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:44,158 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye
# 2026-06-04 18:25:44,627 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Ongoing chunk window exceeded the limit of 150 chunks. Processing.
# 2026-06-04 18:25:44,639 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Got 150 audio chunks from the queue to process.
# 2026-06-04 18:25:44,645 [MainProcess TranscriptorManager   ] DEBUG    pitxu        Sending chunks window to be transcribed into the process
# 2026-06-04 18:25:44,653 [FWhisperStr MainThread            ] DEBUG    pitxu        Xprocess [FWhisperStr] run() received a [TRANSCRIBE_CHUNK_WINDOW: <class 'list'>]
# 2026-06-04 18:25:44,653 [FWhisperStr MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 150 audio chunks with the context of the last overlap and the ongoing transcription.
# 2026-06-04 18:25:44,703 [FWhisperStr MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 150 audio chunks with a total of 53200 samples, with an overlap of 2000 samples from the previous chunk.
# 2026-06-04 18:25:44,703 [FWhisperStr MainThread            ] INFO     faster_whisper Processing audio with duration 00:03.325
# 2026-06-04 18:25:45,170 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:45,187 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye
# 2026-06-04 18:25:46,158 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:46,158 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye
# 2026-06-04 18:25:47,162 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:47,169 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye
# 2026-06-04 18:25:47,655 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------------------------------------------------
# 2026-06-04 18:25:47,656 [FWhisperStr MainThread            ] DEBUG    pitxu        |                              Segments info                              |
# 2026-06-04 18:25:47,656 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------------------------------------------------
# 2026-06-04 18:25:47,656 [FWhisperStr MainThread            ] DEBUG    pitxu        |  Thanks for watching!: start: 1.0 (1.86), end: 2.62 (3.48), prob: -0.88 |
# 2026-06-04 18:25:47,657 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------------------------------------------------
# 2026-06-04 18:25:47,657 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------------------------------------
# 2026-06-04 18:25:47,657 [FWhisperStr MainThread            ] DEBUG    pitxu        |                          Words info                         |
# 2026-06-04 18:25:47,658 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------------------------------------
# 2026-06-04 18:25:47,658 [FWhisperStr MainThread            ] DEBUG    pitxu        |  for      : start: 1.66 (3.52), end: 2.04 (3.9), prob: 0.7  |
# 2026-06-04 18:25:47,658 [FWhisperStr MainThread            ] DEBUG    pitxu        |  watching!: start: 2.04 (3.9), end: 2.62 (4.48), prob: 0.96 |
# 2026-06-04 18:25:47,659 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------------------------------------
# 2026-06-04 18:25:47,659 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:25:47,659 [FWhisperStr MainThread            ] DEBUG    pitxu        |   Low confidence words (0.1)  |
# 2026-06-04 18:25:47,659 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:25:47,660 [FWhisperStr MainThread            ] DEBUG    pitxu        |  Thanks: 0.008684676140546799 |
# 2026-06-04 18:25:47,660 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:25:47,660 [FWhisperStr MainThread            ] DEBUG    pitxu        ✏️ Current ongoing transcription: 

# Goodbye for watching!

# 2026-06-04 18:25:47,661 [FWhisperStr MainThread            ] DEBUG    pitxu        ✏️ Current committed transcription: 

#  Goodbye

# 2026-06-04 18:25:47,836 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Ongoing chunk window exceeded the limit of 150 chunks. Processing.
# 2026-06-04 18:25:47,836 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Got 150 audio chunks from the queue to process.
# 2026-06-04 18:25:47,842 [MainProcess TranscriptorManager   ] DEBUG    pitxu        Sending chunks window to be transcribed into the process
# 2026-06-04 18:25:47,861 [FWhisperStr MainThread            ] DEBUG    pitxu        Xprocess [FWhisperStr] run() received a [TRANSCRIBE_CHUNK_WINDOW: <class 'list'>]
# 2026-06-04 18:25:47,862 [FWhisperStr MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 150 audio chunks with the context of the last overlap and the ongoing transcription.
# 2026-06-04 18:25:47,907 [FWhisperStr MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 150 audio chunks with a total of 53200 samples, with an overlap of 2000 samples from the previous chunk.
# 2026-06-04 18:25:47,908 [FWhisperStr MainThread            ] INFO     faster_whisper Processing audio with duration 00:03.325
# 2026-06-04 18:25:48,170 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:48,193 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching!
# 2026-06-04 18:25:49,164 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:49,176 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching!
# 2026-06-04 18:25:49,235 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------------------------------------------------
# 2026-06-04 18:25:49,235 [FWhisperStr MainThread            ] DEBUG    pitxu        |                              Segments info                              |
# 2026-06-04 18:25:49,236 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------------------------------------------------
# 2026-06-04 18:25:49,236 [FWhisperStr MainThread            ] DEBUG    pitxu        |  Thanks for watching!: start: 0.0 (4.48), end: 3.06 (7.54), prob: -0.71 |
# 2026-06-04 18:25:49,236 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------------------------------------------------
# 2026-06-04 18:25:49,237 [FWhisperStr MainThread            ] DEBUG    pitxu        ----------------------------------------------------------------
# 2026-06-04 18:25:49,237 [FWhisperStr MainThread            ] DEBUG    pitxu        |                          Words info                          |
# 2026-06-04 18:25:49,237 [FWhisperStr MainThread            ] DEBUG    pitxu        ----------------------------------------------------------------
# 2026-06-04 18:25:49,238 [FWhisperStr MainThread            ] DEBUG    pitxu        |  for      : start: 1.64 (6.12), end: 3.04 (7.52), prob: 0.21 |
# 2026-06-04 18:25:49,238 [FWhisperStr MainThread            ] DEBUG    pitxu        |  watching!: start: 3.04 (7.52), end: 3.06 (7.54), prob: 0.91 |
# 2026-06-04 18:25:49,238 [FWhisperStr MainThread            ] DEBUG    pitxu        ----------------------------------------------------------------
# 2026-06-04 18:25:49,239 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:25:49,239 [FWhisperStr MainThread            ] DEBUG    pitxu        |   Low confidence words (0.1)  |
# 2026-06-04 18:25:49,239 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:25:49,239 [FWhisperStr MainThread            ] DEBUG    pitxu        |  Thanks: 0.010770720429718494 |
# 2026-06-04 18:25:49,240 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:25:49,240 [FWhisperStr MainThread            ] DEBUG    pitxu        ✏️ Current ongoing transcription: 

# for watching! for watching!

# 2026-06-04 18:25:49,241 [FWhisperStr MainThread            ] DEBUG    pitxu        ✏️ Current committed transcription: 

#  Goodbye for watching!

# 2026-06-04 18:25:50,168 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:50,204 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching! for watching!
# 2026-06-04 18:25:51,163 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:51,169 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching! for watching!
# 2026-06-04 18:25:51,195 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Ongoing chunk window exceeded the limit of 150 chunks. Processing.
# 2026-06-04 18:25:51,201 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Got 150 audio chunks from the queue to process.
# 2026-06-04 18:25:51,213 [MainProcess TranscriptorManager   ] DEBUG    pitxu        Sending chunks window to be transcribed into the process
# 2026-06-04 18:25:51,225 [FWhisperStr MainThread            ] DEBUG    pitxu        Xprocess [FWhisperStr] run() received a [TRANSCRIBE_CHUNK_WINDOW: <class 'list'>]
# 2026-06-04 18:25:51,226 [FWhisperStr MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 150 audio chunks with the context of the last overlap and the ongoing transcription.
# 2026-06-04 18:25:51,270 [FWhisperStr MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 150 audio chunks with a total of 53200 samples, with an overlap of 2000 samples from the previous chunk.
# 2026-06-04 18:25:51,271 [FWhisperStr MainThread            ] INFO     faster_whisper Processing audio with duration 00:03.325
# 2026-06-04 18:25:52,174 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:52,180 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching! for watching!
# 2026-06-04 18:25:53,184 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:53,190 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching! for watching!
# 2026-06-04 18:25:54,056 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------------------------------------------------
# 2026-06-04 18:25:54,056 [FWhisperStr MainThread            ] DEBUG    pitxu        |                              Segments info                              |
# 2026-06-04 18:25:54,057 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------------------------------------------------
# 2026-06-04 18:25:54,057 [FWhisperStr MainThread            ] DEBUG    pitxu        |  Thanks for watching!: start: 1.9 (9.44), end: 2.96 (10.5), prob: -0.54 |
# 2026-06-04 18:25:54,057 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------------------------------------------------
# 2026-06-04 18:25:54,058 [FWhisperStr MainThread            ] DEBUG    pitxu        ------------------------------------------------------------------
# 2026-06-04 18:25:54,058 [FWhisperStr MainThread            ] DEBUG    pitxu        |                           Words info                           |
# 2026-06-04 18:25:54,058 [FWhisperStr MainThread            ] DEBUG    pitxu        ------------------------------------------------------------------
# 2026-06-04 18:25:54,059 [FWhisperStr MainThread            ] DEBUG    pitxu        |  for      : start: 2.18 (11.62), end: 2.38 (11.82), prob: 0.25 |
# 2026-06-04 18:25:54,059 [FWhisperStr MainThread            ] DEBUG    pitxu        |  watching!: start: 2.38 (11.82), end: 2.96 (12.4), prob: 0.88  |
# 2026-06-04 18:25:54,059 [FWhisperStr MainThread            ] DEBUG    pitxu        ------------------------------------------------------------------
# 2026-06-04 18:25:54,060 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:25:54,060 [FWhisperStr MainThread            ] DEBUG    pitxu        |   Low confidence words (0.1)  |
# 2026-06-04 18:25:54,060 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:25:54,061 [FWhisperStr MainThread            ] DEBUG    pitxu        |  Thanks: 0.009013224393129349 |
# 2026-06-04 18:25:54,061 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:25:54,061 [FWhisperStr MainThread            ] DEBUG    pitxu        ✏️ Current ongoing transcription: 

# for watching! for watching!

# 2026-06-04 18:25:54,062 [FWhisperStr MainThread            ] DEBUG    pitxu        ✏️ Current committed transcription: 

#  Goodbye for watching! for watching!

# 2026-06-04 18:25:54,159 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:54,159 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching! for watching! for watching!
# 2026-06-04 18:25:54,434 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Ongoing chunk window exceeded the limit of 150 chunks. Processing.
# 2026-06-04 18:25:54,439 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Got 150 audio chunks from the queue to process.
# 2026-06-04 18:25:54,457 [MainProcess TranscriptorManager   ] DEBUG    pitxu        Sending chunks window to be transcribed into the process
# 2026-06-04 18:25:54,471 [FWhisperStr MainThread            ] DEBUG    pitxu        Xprocess [FWhisperStr] run() received a [TRANSCRIBE_CHUNK_WINDOW: <class 'list'>]
# 2026-06-04 18:25:54,471 [FWhisperStr MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 150 audio chunks with the context of the last overlap and the ongoing transcription.
# 2026-06-04 18:25:54,515 [FWhisperStr MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 150 audio chunks with a total of 53200 samples, with an overlap of 2000 samples from the previous chunk.
# 2026-06-04 18:25:54,516 [FWhisperStr MainThread            ] INFO     faster_whisper Processing audio with duration 00:03.325
# 2026-06-04 18:25:55,172 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:55,178 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching! for watching! for watching!
# 2026-06-04 18:25:56,152 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:56,169 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching! for watching! for watching!
# 2026-06-04 18:25:57,156 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:57,169 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching! for watching! for watching!
# 2026-06-04 18:25:57,258 [FWhisperStr MainThread            ] DEBUG    pitxu        ----------------------------------------------------------------------------
# 2026-06-04 18:25:57,259 [FWhisperStr MainThread            ] DEBUG    pitxu        |                              Segments info                               |
# 2026-06-04 18:25:57,259 [FWhisperStr MainThread            ] DEBUG    pitxu        ----------------------------------------------------------------------------
# 2026-06-04 18:25:57,259 [FWhisperStr MainThread            ] DEBUG    pitxu        |  Thanks for watching!: start: 1.9 (14.3), end: 3.08 (15.48), prob: -0.54 |
# 2026-06-04 18:25:57,260 [FWhisperStr MainThread            ] DEBUG    pitxu        ----------------------------------------------------------------------------
# 2026-06-04 18:25:57,260 [FWhisperStr MainThread            ] DEBUG    pitxu        ------------------------------------------------------------------
# 2026-06-04 18:25:57,260 [FWhisperStr MainThread            ] DEBUG    pitxu        |                           Words info                           |
# 2026-06-04 18:25:57,261 [FWhisperStr MainThread            ] DEBUG    pitxu        ------------------------------------------------------------------
# 2026-06-04 18:25:57,261 [FWhisperStr MainThread            ] DEBUG    pitxu        |  for      : start: 2.92 (17.22), end: 2.92 (17.22), prob: 0.47 |
# 2026-06-04 18:25:57,261 [FWhisperStr MainThread            ] DEBUG    pitxu        |  watching!: start: 2.92 (17.22), end: 3.08 (17.38), prob: 0.9  |
# 2026-06-04 18:25:57,261 [FWhisperStr MainThread            ] DEBUG    pitxu        ------------------------------------------------------------------
# 2026-06-04 18:25:57,262 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:25:57,262 [FWhisperStr MainThread            ] DEBUG    pitxu        |   Low confidence words (0.1)  |
# 2026-06-04 18:25:57,262 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:25:57,263 [FWhisperStr MainThread            ] DEBUG    pitxu        |  Thanks: 0.002600264037027955 |
# 2026-06-04 18:25:57,263 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:25:57,263 [FWhisperStr MainThread            ] DEBUG    pitxu        ✏️ Current ongoing transcription: 

# for watching! for watching!

# 2026-06-04 18:25:57,264 [FWhisperStr MainThread            ] DEBUG    pitxu        ✏️ Current committed transcription: 

#  Goodbye for watching! for watching! for watching!

# 2026-06-04 18:25:57,683 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Ongoing chunk window exceeded the limit of 150 chunks. Processing.
# 2026-06-04 18:25:57,696 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Got 150 audio chunks from the queue to process.
# 2026-06-04 18:25:57,702 [MainProcess TranscriptorManager   ] DEBUG    pitxu        Sending chunks window to be transcribed into the process
# 2026-06-04 18:25:57,716 [FWhisperStr MainThread            ] DEBUG    pitxu        Xprocess [FWhisperStr] run() received a [TRANSCRIBE_CHUNK_WINDOW: <class 'list'>]
# 2026-06-04 18:25:57,716 [FWhisperStr MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 150 audio chunks with the context of the last overlap and the ongoing transcription.
# 2026-06-04 18:25:57,761 [FWhisperStr MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 150 audio chunks with a total of 53200 samples, with an overlap of 2000 samples from the previous chunk.
# 2026-06-04 18:25:57,762 [FWhisperStr MainThread            ] INFO     faster_whisper Processing audio with duration 00:03.325
# 2026-06-04 18:25:58,167 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:58,167 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching! for watching! for watching! for watching!
# 2026-06-04 18:25:58,277 [MainProcess VADWorker             ] WARNING  pitxu        🟠 VAD detected speech chunk in unexpected IDLE, discarding 2 ongoing chunks. Expected one of: ['START_CONTEXT', 'ONGOING_PROCESS_CHUNK']
# 2026-06-04 18:25:58,277 [MainProcess VADWorker             ] DEBUG    pitxu        🗣️ VAD detected speech end
# 2026-06-04 18:25:58,329 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Received None data from the queue, It should be the end of the stream.
# 2026-06-04 18:25:58,339 [Support     MainThread            ] DEBUG    pitxu        💾 Dumped audio [614402 bytes] of [int16] at [16000 Hz] to file: storage/audio/input/audio_2026-06-04-18-25-58-337783.wav
# 2026-06-04 18:25:58,342 [Support     MainThread            ] DEBUG    pitxu        💾 Dumped audio [614402 bytes] of [int16] at [16000 Hz] to file: storage/audio/preprocessed_input/audio_2026-06-04-18-25-58-337783.wav
# 2026-06-04 18:25:58,349 [Support     MainThread            ] DEBUG    matplotlib.pyplot Loaded backend Agg version v2.2.
# 2026-06-04 18:25:58,349 [MainProcess TranscriptorManager   ] DEBUG    pitxu        👁️‍🗨️ Transitioning from ONGOING_PROCESS_CHUNK to LEFTOVER_CHUNK_PROCESSING
# 2026-06-04 18:25:58,366 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Still 31 leftover audio chunks from the queue to process.
# 2026-06-04 18:25:58,372 [MainProcess TranscriptorManager   ] DEBUG    pitxu        Sending chunks window to be transcribed into the process
# 2026-06-04 18:25:58,383 [MainProcess TranscriptorManager   ] DEBUG    pitxu        Requesting transcription result from the process
# 2026-06-04 18:25:58,389 [MainProcess TranscriptorManager   ] DEBUG    pitxu        👁️‍🗨️ Transitioning from LEFTOVER_CHUNK_PROCESSING to REQUESTED_TRANSCRIPTION
# 2026-06-04 18:25:59,150 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:25:59,163 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching! for watching! for watching! for watching!
# 2026-06-04 18:26:00,157 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:26:00,157 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching! for watching! for watching! for watching!
# 2026-06-04 18:26:01,153 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:26:01,161 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching! for watching! for watching! for watching!
# 2026-06-04 18:26:02,154 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:26:02,160 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching! for watching! for watching! for watching!
# 2026-06-04 18:26:02,832 [FWhisperStr MainThread            ] DEBUG    pitxu        ------------------------------------------------------------------------------
# 2026-06-04 18:26:02,833 [FWhisperStr MainThread            ] DEBUG    pitxu        |                               Segments info                                |
# 2026-06-04 18:26:02,834 [FWhisperStr MainThread            ] DEBUG    pitxu        ------------------------------------------------------------------------------
# 2026-06-04 18:26:02,834 [FWhisperStr MainThread            ] DEBUG    pitxu        |  Thanks for watching!: start: 2.48 (19.86), end: 2.88 (20.26), prob: -0.62 |
# 2026-06-04 18:26:02,834 [FWhisperStr MainThread            ] DEBUG    pitxu        ------------------------------------------------------------------------------
# 2026-06-04 18:26:02,835 [FWhisperStr MainThread            ] DEBUG    pitxu        ------------------------------------------------------------------
# 2026-06-04 18:26:02,835 [FWhisperStr MainThread            ] DEBUG    pitxu        |                           Words info                           |
# 2026-06-04 18:26:02,836 [FWhisperStr MainThread            ] DEBUG    pitxu        ------------------------------------------------------------------
# 2026-06-04 18:26:02,836 [FWhisperStr MainThread            ] DEBUG    pitxu        |  for      : start: 2.48 (22.34), end: 2.86 (22.72), prob: 0.44 |
# 2026-06-04 18:26:02,836 [FWhisperStr MainThread            ] DEBUG    pitxu        |  watching!: start: 2.86 (22.72), end: 2.88 (22.74), prob: 0.91 |
# 2026-06-04 18:26:02,837 [FWhisperStr MainThread            ] DEBUG    pitxu        ------------------------------------------------------------------
# 2026-06-04 18:26:02,837 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:26:02,837 [FWhisperStr MainThread            ] DEBUG    pitxu        |   Low confidence words (0.1)  |
# 2026-06-04 18:26:02,837 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:26:02,838 [FWhisperStr MainThread            ] DEBUG    pitxu        |  Thanks: 0.006220690440386534 |
# 2026-06-04 18:26:02,838 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:26:02,839 [FWhisperStr MainThread            ] DEBUG    pitxu        ✏️ Current ongoing transcription: 

# for watching! for watching!

# 2026-06-04 18:26:02,839 [FWhisperStr MainThread            ] DEBUG    pitxu        ✏️ Current committed transcription: 

#  Goodbye for watching! for watching! for watching! for watching!

# 2026-06-04 18:26:02,839 [FWhisperStr MainThread            ] DEBUG    pitxu        Xprocess [FWhisperStr] run() received a [TRANSCRIBE_CHUNK_WINDOW: <class 'list'>]
# 2026-06-04 18:26:02,840 [FWhisperStr MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 31 audio chunks with the context of the last overlap and the ongoing transcription.
# 2026-06-04 18:26:02,850 [FWhisperStr MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 31 audio chunks with a total of 12581 samples, with an overlap of 2000 samples from the previous chunk.
# 2026-06-04 18:26:02,850 [FWhisperStr MainThread            ] INFO     faster_whisper Processing audio with duration 00:00.786
# 2026-06-04 18:26:03,120 [MainProcess VADWorker             ] WARNING  pitxu        🟠 VAD detected speech start but the current state is not IDLE: REQUESTED_TRANSCRIPTION
# 2026-06-04 18:26:03,173 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:26:03,184 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching! for watching! for watching! for watching! for watching!
# 2026-06-04 18:26:04,169 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-04 18:26:04,179 [FWhisperStr MainThread            ] DEBUG    pitxu        ----------------------------------------------------------------------------
# 2026-06-04 18:26:04,180 [FWhisperStr MainThread            ] DEBUG    pitxu        |                              Segments info                               |
# 2026-06-04 18:26:04,180 [FWhisperStr MainThread            ] DEBUG    pitxu        ----------------------------------------------------------------------------
# 2026-06-04 18:26:04,181 [FWhisperStr MainThread            ] DEBUG    pitxu        |  Thanks for watching!: start: 0.0 (22.74), end: 0.4 (23.14), prob: -0.65 |
# 2026-06-04 18:26:04,181 [FWhisperStr MainThread            ] DEBUG    pitxu        ----------------------------------------------------------------------------
# 2026-06-04 18:26:04,181 [FWhisperStr MainThread            ] DEBUG    pitxu        -----------------------------------------------------------------
# 2026-06-04 18:26:04,182 [FWhisperStr MainThread            ] DEBUG    pitxu        |                           Words info                          |
# 2026-06-04 18:26:04,182 [FWhisperStr MainThread            ] DEBUG    pitxu        -----------------------------------------------------------------
# 2026-06-04 18:26:04,182 [FWhisperStr MainThread            ] DEBUG    pitxu        |  for      : start: 0.0 (22.74), end: 0.28 (23.02), prob: 0.54 |
# 2026-06-04 18:26:04,183 [FWhisperStr MainThread            ] DEBUG    pitxu        |  watching!: start: 0.28 (23.02), end: 0.4 (23.14), prob: 0.91 |
# 2026-06-04 18:26:04,183 [FWhisperStr MainThread            ] DEBUG    pitxu        -----------------------------------------------------------------
# 2026-06-04 18:26:04,183 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:26:04,184 [FWhisperStr MainThread            ] DEBUG    pitxu        |   Low confidence words (0.1)  |
# 2026-06-04 18:26:04,184 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:26:04,184 [FWhisperStr MainThread            ] DEBUG    pitxu        |  Thanks: 0.005382917821407318 |
# 2026-06-04 18:26:04,185 [FWhisperStr MainThread            ] DEBUG    pitxu        ---------------------------------
# 2026-06-04 18:26:04,185 [FWhisperStr MainThread            ] DEBUG    pitxu        ✏️ Current ongoing transcription: 

# for watching! for watching!

# 2026-06-04 18:26:04,186 [FWhisperStr MainThread            ] DEBUG    pitxu        ✏️ Current committed transcription: 



# 2026-06-04 18:26:04,186 [FWhisperStr MainThread            ] DEBUG    pitxu        Xprocess [FWhisperStr] run() received a [RETRIEVE_TRANSCRIPTION_RESULT]
# 2026-06-04 18:26:04,186 [FWhisperStr MainThread            ] DEBUG    pitxu        ✏️ Final transcription: 

# Goodbye for watching! for watching! for watching! for watching! for watching! for watching!

# 2026-06-04 18:26:04,187 [FWhisperStr MainThread            ] DEBUG    pitxu        Final transcription put in the output queue.
# 2026-06-04 18:26:04,182 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 STT processing: ongoing transcription: Goodbye for watching! for watching! for watching! for watching! for watching!
# 2026-06-04 18:26:04,274 [MainProcess TranscriptorManager   ] DEBUG    pitxu        👁️‍🗨️ Transitioning from REQUESTED_TRANSCRIPTION to FINAL_TRANSCRIPTION
# 2026-06-04 18:26:04,287 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Got transcription result from the Process: Goodbye for watching! for watching! for watching! for watching! for watching! for watching!
# 2026-06-04 18:26:04,293 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Merging transcription result with the final transcription.
# 2026-06-04 18:26:04,311 [MainProcess TranscriptorManager   ] DEBUG    pitxu        👁️‍🗨️ Transitioning from FINAL_TRANSCRIPTION to DONE
# 2026-06-04 18:26:04,317 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Triggering on_transcription_finished_callback callback after receiving transcription result from the Process.
# 2026-06-04 18:26:04,335 [MainProcess TranscriptorManager   ] DEBUG    pitxu        👁️‍🗨️ Transitioning from DONE to IDLE
# 2026-06-04 18:26:04,342 [MainProcess MainThread            ] INFO     pitxu        Main execution triggered by user finishing speaking, via Transcription callback.
# 2026-06-04 18:26:04,468 [MainProcess MainThread            ] DEBUG    pitxu        Getting transcription from STT after VAD detected speech finished, for streaming engine...
# 2026-06-04 18:26:04,480 [MainProcess MainThread            ] DEBUG    pitxu        💬 Recognised dictate: Goodbye for watching! for watching! for watching! for watching! for watching! for watching!
# 2026-06-04 18:26:04,492 [MainProcess MainThread            ] DEBUG    pitxu        ⏱️  Dictate 0: 0.0246
# 2026-06-04 18:26:04,504 [MainProcess MainThread            ] DEBUG    pitxu        Checking if text has exit intention: 'Goodbye for watching! for watching! for watching! for watching! for watching! for watching!' -> 'goodbye for watching! for watching! for watching! for watching! for watching! for watching!': False
# 2026-06-04 18:26:04,517 [MainProcess MainThread            ] DEBUG    pitxu        Detection: Text intends to trigger or continue an interaction.
# 2026-06-04 18:26:04,517 [MainProcess MainThread            ] DEBUG    pitxu        🤖 Triggering thinking interaction on background display.
# 2026-06-04 18:26:04,523 [DsiLcd      MainThread            ] INFO     pitxu        🤖 Showing KITT thinking on DSI LCD.
# 2026-06-04 18:26:04,530 [DsiLcd      MainThread            ] INFO     pitxu        👀 Showing arbitrary text on DSI LCD while thinking.
# 2026-06-04 18:26:04,542 [MainProcess MainThread            ] DEBUG    pitxu        Waiting for queue dsi_lcd_queue to empty. Has now: 0 elements.
# 2026-06-04 18:26:04,573 [MainProcess MainThread            ] DEBUG    pitxu        The queue dsi_lcd_queue is empty now. I've sleept 0s.
# 2026-06-04 18:26:04,585 [MainProcess MainThread            ] INFO     pitxu        ❓ Question in Chatbot: 

# >> Goodbye for watching! for watching! for watching! for watching! for watching! for watching!

# ISSUE 2
# At the very end of the conversation, I expected to be able to say GoodBye and close the app, but
# apparently the callback "user_intends_to_end_conversation" may have anything to do for the wronf state of the STT. 

# 2026-05-31 22:09:55,283 [FasterWhisperStream MainThread            ] DEBUG    pitxu        Xprocess [FasterWhisperStream] run() received a [RETRIEVE_TRANSCRIPTION_RESULT]
# 2026-05-31 22:09:55,284 [FasterWhisperStream MainThread            ] DEBUG    pitxu        Final transcription put in the output queue with the sentinel.
# 2026-05-31 22:09:55,388 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Got transcription result from the Process: This is the end for tonight. Thank you very much.
# 2026-05-31 22:09:55,388 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Merging transcription result with the final transcription.
# 2026-05-31 22:09:55,388 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Triggering on_transcription_finished_callback callback after receiving transcription result from the Process.
# 2026-05-31 22:09:55,388 [MainProcess MainThread            ] INFO     pitxu        Main execution triggered by user finishing speaking, via Transcription callback.
# 2026-05-31 22:09:55,388 [MainProcess MainThread            ] DEBUG    pitxu        🔇 Stopping the input stream as microphone is muting.
# 2026-05-31 22:09:55,494 [MainProcess MainThread            ] DEBUG    pitxu        🔇 Muting the microphone. Now mute is [True]
# 2026-05-31 22:09:55,494 [MainProcess MainThread            ] DEBUG    pitxu        Getting transcription from STT after VAD detected speech finished, for streaming engine...
# 2026-05-31 22:09:55,494 [MainProcess MainThread            ] DEBUG    pitxu        💬 Recognised dictate: This is the end for tonight. Thank you very much.
# 2026-05-31 22:09:55,494 [MainProcess MainThread            ] DEBUG    pitxu        ⏱️  Dictate 10: 0.0001
# 2026-05-31 22:09:55,494 [MainProcess MainThread            ] DEBUG    pitxu        Checking if text has exit intention: 'This is the end for tonight. Thank you very much.' -> 'this is the end for tonight thank you very much': False
# 2026-05-31 22:09:55,494 [MainProcess MainThread            ] DEBUG    pitxu        Detection: Text intends to trigger or continue an interaction.
# 2026-05-31 22:09:55,494 [MainProcess MainThread            ] DEBUG    pitxu        💤  Setting idle mode off.
# 2026-05-31 22:09:55,494 [MainProcess MainThread            ] DEBUG    pitxu        🤖 Triggering thinking interaction on background display.
# 2026-05-31 22:09:55,494 [MainProcess MainThread            ] DEBUG    pitxu        Waiting for queue dsi_lcd_queue to empty. Has now: 1 elements.
# 2026-05-31 22:09:55,506 [DsiLcd      MainThread            ] INFO     pitxu        🤖 Showing KITT thinking on DSI LCD.
# 2026-05-31 22:09:55,518 [DsiLcd      MainThread            ] INFO     pitxu        👀 Showing arbitrary text on DSI LCD while thinking.
# 2026-05-31 22:09:56,000 [MainProcess MainThread            ] DEBUG    pitxu        The queue dsi_lcd_queue is empty now. I've sleept 0.5s.
# 2026-05-31 22:09:56,000 [MainProcess MainThread            ] DEBUG    pitxu        🤖 Setting Chatbot as busy.
# 2026-05-31 22:09:56,000 [MainProcess MainThread            ] INFO     pitxu        ❓ Question: 

# >> This is the end for tonight. Thank you very much.

# 2026-05-31 22:09:56,000 [MainProcess MainThread            ] INFO     google_genai.models AFC is enabled with max remote calls: 10.
# 2026-05-31 22:09:57,632 [MainProcess MainThread            ] INFO     httpx        HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent "HTTP/1.1 200 OK"
# 2026-05-31 22:09:57,634 [MainProcess asyncio_0             ] INFO     pitxu        User intends to end the conversation.
# 2026-05-31 22:10:00,071 [MainProcess MainThread            ] INFO     httpx        HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent "HTTP/1.1 200 OK"
# 2026-05-31 22:10:00,072 [MainProcess MainThread            ] INFO     pitxu        🗣️  Answer: 

# >> You're very welcome, Xavi. It was a productive day. Sleep well, and I'll be here whenever you need me next. Good night.

# 2026-05-31 22:10:00,073 [MainProcess MainThread            ] DEBUG    pitxu        🤖 Unsetting Chatbot as busy.
# 2026-05-31 22:10:00,073 [MainProcess MainThread            ] INFO     pitxu        Reacting to a Chatbot answer: 
#         - Text: You're very welcome, Xavi. It was a productive day. Sleep well, and I'll be here whenever you need me next. Good night.
#         - Function Calls: ['user_intends_to_end_conversation']
#         - Code blocks: 0
# 2026-05-31 22:10:00,073 [MainProcess MainThread            ] DEBUG    pitxu        ⚡️ Reacting to function call: user_intends_to_end_conversation
# 2026-05-31 22:10:00,073 [MainProcess MainThread            ] DEBUG    pitxu        🏁 Handling end of conversation request...
# 2026-05-31 22:10:00,073 [MainProcess MainThread            ] INFO     pitxu        🏁 End of conversation request handled successfully.
# 2026-05-31 22:10:00,073 [MainProcess MainThread            ] DEBUG    pitxu        Waiting for queue dsi_lcd_queue to empty. Has now: 0 elements.
# 2026-05-31 22:10:00,073 [MainProcess MainThread            ] DEBUG    pitxu        The queue dsi_lcd_queue is empty now. I've sleept 0s.
# 2026-05-31 22:10:00,077 [MainProcess MainThread            ] DEBUG    pitxu        🗣️ Triggering speech interaction: You're very welcome, Xavi. It was a productive day. Sleep well, and I'll be here whenever you need me next. Good night.
# 2026-05-31 22:10:00,077 [MainProcess MainThread            ] DEBUG    pitxu        🗣️ Sending SAY command to Background display
# 2026-05-31 22:10:00,077 [MainProcess MainThread            ] DEBUG    pitxu        🗣️ Sending SAY command to Speaker
# 2026-05-31 22:10:00,078 [MainProcess MainThread            ] DEBUG    pitxu        🗣️ Waiting for Speaker and Display to start and finish speaking
# 2026-05-31 22:10:00,078 [MainProcess MainThread            ] DEBUG    pitxu        Waiting for the process speaker_busy to be busy. It's now: IDLE.
# 2026-05-31 22:10:00,078 [DsiLcd      MainThread            ] INFO     pitxu        👄 Showing KITT mouth on DSI LCD.
# 2026-05-31 22:10:00,078 [Piper       MainThread            ] DEBUG    pitxu        Saying [You're very welcome, Chabee. It was a productive day. Sleep well, and I'll be here whenever you need me next. Good night.]
# 2026-05-31 22:10:00,088 [MainProcess MainThread            ] DEBUG    pitxu        The process speaker_busy is busy now. I've slept 0.01s.
# 2026-05-31 22:10:00,088 [MainProcess MainThread            ] DEBUG    pitxu        Waiting for the process speaker_busy to idle. It's now: BUSY.
# 2026-05-31 22:10:06,975 [MainProcess MainThread            ] DEBUG    pitxu        The process speaker_busy is idle now. I've slept 5.9s.
# 2026-05-31 22:10:06,975 [MainProcess MainThread            ] DEBUG    pitxu        Waiting for the process dsi_lcd_busy to idle. It's now: IDLE.
# 2026-05-31 22:10:06,975 [MainProcess MainThread            ] DEBUG    pitxu        The process dsi_lcd_busy is idle now. I've slept 0s.
# 2026-05-31 22:10:06,976 [MainProcess MainThread            ] DEBUG    pitxu        ⏱️  Answer 10: 6.8983
# 2026-05-31 22:10:06,976 [MainProcess MainThread            ] DEBUG    pitxu        🔊 Starting the input stream as microphone is unmuting.
# 2026-05-31 22:10:07,027 [MainProcess MainThread            ] DEBUG    pitxu        🔊 Unmuting the microphone. Now mute is [False]
# 2026-05-31 22:10:07,844 [MainProcess ThreadPoolExecutor-0_1] DEBUG    pitxu        ⏳ Waiting for an user interaction. 94% (paused 0s) time left.
# 2026-05-31 22:10:07,844 [MainProcess ThreadPoolExecutor-0_1] DEBUG    pitxu        🚥 Showing interaction holding percentage 94% on background display
# 2026-05-31 22:10:07,850 [DsiLcd      MainThread            ] INFO     pitxu        🚥 Showing interaction holding percentage 94% on DSI LCD
# 2026-05-31 22:10:08,180 [MainProcess Dummy-17              ] DEBUG    pitxu        🗣️ VAD detected speech start
# 2026-05-31 22:10:08,181 [MainProcess MainThread            ] INFO     pitxu        VAD detected speech, via VAD callback.
# 2026-05-31 22:10:08,181 [MainProcess MainThread            ] DEBUG    pitxu        🗣️ Resetting Dictate context on VAD detected speech start.
# 2026-05-31 22:10:08,181 [MainProcess MainThread            ] WARNING  pitxu        🟠 Trying to reset context while the transcription is not in IDLE or DONE state. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,182 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,182 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,182 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,182 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,182 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,182 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,182 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,182 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,284 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,285 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,285 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,285 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,390 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,390 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,390 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,390 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,390 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,493 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,493 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,493 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,493 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,493 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,599 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,599 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,599 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,599 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,599 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,701 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,701 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,701 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,701 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,702 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,807 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
# 2026-05-31 22:10:08,807 [MainProcess TranscriptorManager   ] WARNING  pitxu        🟠 Received audio chunk while the transcription is not in a state to consume it. Current state: ONGOING_PROCESS_CHUNK.
