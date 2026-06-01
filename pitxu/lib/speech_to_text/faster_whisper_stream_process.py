import logging

from pyxavi import Config, Dictionary, TerminalColor, full_stack, dd
from pitxu.lib.speech_to_text.preprocess.preprocessor import Preprocessor
from pitxu.lib.speech_to_text.speech_to_text import SpeechToTextException
from pitxu.lib.utils.xprocess_pool import XprocessPool
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction

import queue
from faster_whisper import WhisperModel
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
    _use_segment_low_confidence_threshold = False
    _segment_low_confidence_threshold = -0.8
    _use_word_low_confidence_threshold = False
    _word_low_confidence_threshold = 0.2
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
    # The current (or final) transcription
    # CHANGED: We try to store also timestamps and correct previous partials with newer partials
    # _ongoing_transcription = ""
    _ongoing_transcription:list[dict] = [] # List of dict with "text", "start" and "end" of the transcription, to be able to correct previous partials with newer partials, and to have timestamps for the merging process.
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

    # Define a small tolerance window (e.g., 50ms) for word repetition
    TIME_TOLERANCE: float = 0.05

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
            max_prompt_buffer_size_in_chars = int(self._xconfig.get("speech-to-text.faster_whisper_streaming.max_prompt_buffer_size_in_chars", 100))
            hallucination_silence_threshold = float(self._xconfig.get("speech-to-text.faster_whisper_streaming.hallucination_silence_threshold", 1.0))
            segment_low_confidence_threshold = float(self._xconfig.get("speech-to-text.faster_whisper_streaming.segment_low_confidence_threshold", -0.8))
            word_low_confidence_threshold = float(self._xconfig.get("speech-to-text.faster_whisper_streaming.word_low_confidence_threshold", 0.2))
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
            self._segment_low_confidence_threshold = segment_low_confidence_threshold
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
            logging_parts.append(("Segment low confidence threshold", segment_low_confidence_threshold))
            logging_parts.append(("Word low confidence threshold", word_low_confidence_threshold))
            logging_parts.append(("CPU threads", cpu_threads))
            logging_parts.append(("Overlap size", overlap_size))
            logging_parts.append(("Overlapping chunks duration at 16kHz (ms)", round(overlap_size / 16000 * 1000, 2)))
            logging_parts.append(("Chunks window", chunks_window))
            logging_parts.append(("Sleep when no chunks", sleep_when_no_chunks))
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

        # I can't pass the Support clas to the subprocess, as the Support class is already a subprocess.
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
        # hot_words.extend([self._xconfig.get("chatbot.name")] + self._xconfig.get("chatbot.name_variations", []))
        return hot_words
        
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
        
        if self._preprocessor is not None:
            self._xlog.debug("Deleting STT preprocessor")
            self._preprocessor.close()
            del self._preprocessor
        
        if self._shared_memory is not None:
            self._xlog.debug("Closing Shared Memory from FasterWhisper Stream")
            self._shared_memory.close()
            del self._shared_memory

        # Remember that FasterWhisper Stream is not active anymore
        self.is_active = False

        self._xlog.debug("Done finishing FasterWhisperStream Worker")
    
    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        
        if action == XprocAction.RESET_TRANSCRIPTION:
            self.reset_context()
        
        if action == XprocAction.TRANSCRIBE_CHUNK_WINDOW:
            if isinstance(param, list) and all(isinstance(chunk, bytes) for chunk in param):
                # ⚠️ What is this return? If it puts partials into the queue... whouldn't be this
                # the repetitions that I see? I don't expect elements in the queue but the very final one!
                return self.process_chunks(param)
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
                # The boolean flag is set in the _validate_last_segment_confidence_to_avoid_hallucination method().
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
                # COMMENTED: The model appears to hallucinate with an initial prompt that is not text.
                # elif len(self._ongoing_transcription) == 0:
                #     # It's the first audio to process, so we use the prompt to give some instructions.
                #     prompt = "Please transcribe the following audio. Do not repeat phrases or invent text."
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
                repetition_penalty=1.5,
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
            # new_words = []  # Here will be the commited words after comparing via timestamp.
            new_transcribed_words = []
            # The offsets of the word are from the segment, not the chunk.
            # we need to add the segment offset to the word time.
            current_segment_starting_time = self._last_committed_timestamp
            current_segment_ending_time = self._last_committed_timestamp

            # # These are the flags for the "previous segment", because in the RPi sometimes the model goes crazy
            # #   and repeats the exact same segment in the text, here we check it per words, not per timestamps.
            # #   according to the bugs seen.
            # previous_segments_in_text = []
            # previous_segment = {
            #     "segment": "",
            #     "start": -1,
            #     "end": -1
            # }
            for segment in segments:

                # # Check if the segment is the same AND if the start time is within the tolerance
                # is_segment_duplicate = any(s["segment"].lower().strip() == segment.text.lower().strip() for s in previous_segments_in_text)
                # # If so, skip it.
                # if is_segment_duplicate:
                #     self._log_debug(f"FasterWhisper Stream: Skipping duplicate segment '{segment.text}' (start: {segment.start}, prev_start: {previous_segment['start']})")
                #     continue
                # previous_segments_in_text.append({
                #     "segment": segment.text,
                #     "start": segment.start,
                #     "end": segment.end
                # })


                # # The idea here is to avoid low confidence segments... but it's not fine tunned and then, deactivated by config
                # if self._use_segment_low_confidence_threshold and segment.avg_logprob < self._segment_low_confidence_threshold:
                #     self._log_debug(f"FasterWhisper Stream: Segment with low confidence detected, avg_logprob: {segment.avg_logprob}, text: {segment.text}")
                #     continue

                current_segment_starting_time = current_segment_starting_time + segment.start
                current_segment_ending_time = current_segment_ending_time + segment.end
                seg_infos.append((segment.text, f"start: {round(segment.start, 2)} ({round(current_segment_starting_time, 2)}), end: {round(segment.end, 2)} ({round(current_segment_ending_time, 2)}), prob: {round(segment.avg_logprob, 2)}"))

                # # These are the flags for the "previous word", because in the RPi sometimes the model goes crazy
                # #   and repeats the exact same word un the segment, with the same timestamps (probability is very similar, but not the same),
                # #   so we can check for that and discard it.
                # previous_words_in_segment = []
                # previous_word = {
                #     "word": "",
                #     "start": -1,
                #     "end": -1
                # }

                # Now, every word in this segment.
                for word in segment.words:

                    # This is the logic for the protection about the model going crazy and repeating the exact same word in the segment
                    # ⚠️ still happens
                    # ✅ Fixed: Chunks out of context (next speech) were bein merged into the chunks to be processed, which caused the model to repeat the same segment and words again and again, as it was confused with the previous chunk. Now, the chunk merging process is more accurate, so it does not cause this problem anymore.
                    #   "First I'm going to go out outside for a cigarette. And then I will keep on trying. this is like. window merging. gg. strategy. time. gg. gg. gg. gg. gg. g gg. gg. gg. gg. g gg. gg. gg. gg. gg. gg. gg. g gg. g"
                    # if word.word == previous_word and word.start == previous_start and word.end == previous_end:
                    #     continue

                    # # Check if the word is the same AND if the start time is within the tolerance
                    # is_word_duplicate = any(
                    #     w["word"] == word.word and
                    #     abs(w["start"] - word.start) < self.TIME_TOLERANCE and
                    #     abs(w["end"] - word.end) < self.TIME_TOLERANCE
                    #     for w in previous_words_in_segment
                    # )
                    # # If so, skip it.
                    # if is_word_duplicate:
                    #     self._log_debug(f"FasterWhisper Stream: Skipping duplicate word '{word.word}' (start: {word.start}, prev_start: {previous_word['start']})")
                    #     continue
                    # previous_words_in_segment.append({
                    #     "word": word.word,
                    #     "start": word.start,
                    #     "end": word.end
                    # })

                    # # If the confidence of the word is too low, skip it. 
                    # # This is to avoid hallucinations and wrong merging. Works but not well fine tuned:
                    # #   ⚠️ now it does not recognize the exit word "Goodbye" as correct.
                    # #   ✅ Fixed: Chunks out of context (next speech) were bein merged into the chunks to be processed.
                    # if self._use_word_low_confidence_threshold and word.probability < self._word_low_confidence_threshold:
                    #     self._log_debug(f"FasterWhisper Stream: Word with low confidence detected, probability: {word.probability}, word: {word.word}")
                    #     continue

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

                    # COMMENTED: I believe it messes up with the new merging method.
                    # # Calculate absolute time of the word
                    # absolute_word_start = self._current_chunk_start_time + word.start
                    # absolute_word_end = self._current_chunk_start_time + word.end

                    # # Only commit words that appear after or at our last committed timestamp
                    # # ⚠️ This part prevents that the new partial fixes the issues at the end of the previous segment.
                    # #   but it's secondary, as the main goal is to avoid hallucinations and wrong merging, which it does.
                    # if absolute_word_start >= self._last_committed_timestamp:
                    #     cleaned_word = self._clean_word(word.word)

                    #     if cleaned_word: # Only add if it's not empty/filler
                    #         new_words.append(cleaned_word)
                    #         # Update last committed timestamp using absolute time, ensuring we don't go backwards
                    #         self._last_committed_timestamp = max(self._last_committed_timestamp, absolute_word_end)

            # Just a logging to see the outcome of the analysis.   
            self.log_summary("Segments info", seg_infos, attend_verbose_debug_flag=True)
            self.log_summary("Words info", words_info, attend_verbose_debug_flag=True)

            # # Some protection in case that low confidence segments are the only ones we have, to avoid hallucinations and wrong merging.
            # if len(new_words) == 0:
            #     self._log_debug("FasterWhisper Stream: No valid words to process after transcription, returning empty result.")
            #     result = ""
            # else:
            #     result = " ".join(new_words)

            # 5. Update state
            # self._ongoing_transcription += " " + result if self._ongoing_transcription else result
            self._ongoing_transcription = self._merge_and_correct_transcription(
                self._ongoing_transcription,
                new_transcribed_words
            )

            self._xlog.debug(f"✏️ Current ongoing transcription: \n\n{TerminalColor.ORANGE}{" ".join([w['word'] for w in self._ongoing_transcription])}{TerminalColor.END}\n")

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
                # COMMENTED: We don't want to publish partials. Just to accummulate the final transcription.
                # self._output_queue.put(self._final_transcription)
                # COMMENTED: We already set it above, before the split of the commited words.
                # self._last_committed_timestamp = committed_words[-1]['end']

            # Update the chunk start time for the next iteration
            # COMMENTED: The chunk start time is updated based on the actual audio processed, not on the chunk duration,
            # to be more accurate and to avoid losing time in case of silence or non transcribed audio.
            # self._current_chunk_start_time += chunk_duration

            # Keep the last defined samples as overlap
            self._last_overlap = audio_to_process[-self._overlap_size:]

        self._xlog.debug(f"✏️ Current committed transcription: \n\n{TerminalColor.ORANGE_BRIGHT}{result}{TerminalColor.END}\n")
        return result
    
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
        # cleaned_text = re.sub(r'([^.]*\.\s*){1,2}$', r'\1', cleaned_text).strip()

        return cleaned_text.strip()

    def _validate_last_segment_confidence_to_avoid_hallucination(self, segments: list) -> bool:
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

        # This is just here for reference in the leftover merging below.
        # self._final_transcription += " " + " ".join([w['word'] for w in committed_words])

        # We may still have some ongoing transcription that is not yet committed, so we add them to the final transcription,
        # As we don't expect more partials to correct it.
        leftover_transcription = " ".join([w['word'] for w in self._ongoing_transcription])
        if leftover_transcription:
            self._final_transcription += " " + leftover_transcription if self._final_transcription else leftover_transcription

        # We get the final transcription and use the moment to clean it.
        final_transcription = self._clean_transcription(self._final_transcription)

        self._xlog.debug(f"✏️ Final transcription: \n\n{TerminalColor.RED}{final_transcription}{TerminalColor.END}\n")

        # We put the transcription in the output queue, to be retrieved by the Main process.
        # if self._output_queue is not None and self._output_queue_sentinel is not None:
        if self._output_queue is not None:
            self._output_queue.put(final_transcription)
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

# ISSUE 1
# There is an obvious duplication, apparently due to non-processed leftovers or the non-commited set of words.
# The transcription was correct, but anyhow leftover chunks were processed that gave the SAME outcome and got added to the transcription.
# Could be that the timestamps of these leftover chunks are wrong (like not getting the right offset) and they are 
# simply merged afterwards.
#
# Also could be that because we're adding the overlap in front of the chunk, we should:
#   1. Calculate how much time we're regressing from the previous processed timestamp (processed_timestamp - overlap_duration)
#   2. Add this time to the timestamps of the segments and words returned by the model, to have the real offsets for the merging and the commiting.
#   3. The merging will then find the correct timestamp to write into, that then should identify which word to overwrite, and cancel the duplication.
#
# 2026-06-01 08:22:48,934 [MainProcess MainThread            ] DEBUG    pitxu        ✏️ 👁️‍🗨️ Transcription state updated to START_CONTEXT, welcoming chunks to process.
# 2026-06-01 08:22:48,934 [MainProcess MainThread            ] DEBUG    pitxu        Requesting context reset in the process
# 2026-06-01 08:22:48,934 [FasterWhisperStream MainThread            ] DEBUG    pitxu        Xprocess [FasterWhisperStream] run() received a [RESET_TRANSCRIPTION]
# 2026-06-01 08:22:48,988 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ 👁️‍🗨️ Transcription state updated from start_context to ONGOING_PROCESS_CHUNK, About to process chunks.
# 2026-06-01 08:22:49,737 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-01 08:22:49,738 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        ⏳ Waiting for an user interaction. 95% (paused 1s) time left.
# 2026-06-01 08:22:49,738 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🚥 Showing interaction holding percentage 95% on background display
# 2026-06-01 08:22:49,743 [DsiLcd      MainThread            ] INFO     pitxu        🚥 Showing interaction holding percentage 95% on DSI LCD
# 2026-06-01 08:22:50,739 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-01 08:22:50,739 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        ⏳ Waiting for an user interaction. 95% (paused 2s) time left.
# 2026-06-01 08:22:50,739 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🚥 Showing interaction holding percentage 95% on background display
# 2026-06-01 08:22:50,745 [DsiLcd      MainThread            ] INFO     pitxu        🚥 Showing interaction holding percentage 95% on DSI LCD
# 2026-06-01 08:22:50,882 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Ongoing chunk window exceeded the limit of 100 chunks. Processing.
# 2026-06-01 08:22:50,882 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Got 100 audio chunks from the queue to process.
# 2026-06-01 08:22:50,882 [MainProcess TranscriptorManager   ] DEBUG    pitxu        Sending chunks window to be transcribed into the process
# 2026-06-01 08:22:50,882 [FasterWhisperStream MainThread            ] DEBUG    pitxu        Xprocess [FasterWhisperStream] run() received a [TRANSCRIBE_CHUNK_WINDOW: <class 'list'>]
# 2026-06-01 08:22:50,883 [FasterWhisperStream MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 100 audio chunks with the context of the last overlap and the ongoing transcription.
# 2026-06-01 08:22:50,944 [FasterWhisperStream MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 100 audio chunks with a total of 34133 samples, with an overlap of 0 samples from the previous chunk.
# 2026-06-01 08:22:50,944 [FasterWhisperStream MainThread            ] INFO     faster_whisper Processing audio with duration 00:02.133
# 2026-06-01 08:22:51,471 [MainProcess Dummy-6               ] DEBUG    pitxu        🗣️ VAD detected speech end
# 2026-06-01 08:22:51,513 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Received None data from the queue, It should be the end of the stream.
# 2026-06-01 08:22:51,515 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ 👁️‍🗨️ Transcription state updated from ongoing_process_chunk to LEFTOVER_CHUNK_PROCESSING, Process the leftover chunks.
# 2026-06-01 08:22:51,515 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Still 29 leftover audio chunks from the queue to process.
# 2026-06-01 08:22:51,515 [Support     MainThread            ] DEBUG    pitxu        💾 Dumped audio [68266 bytes] of [int16] at [16000 Hz] to file: storage/audio/input/audio_2026-06-01-08-22-51-514475.wav
# 2026-06-01 08:22:51,515 [MainProcess TranscriptorManager   ] DEBUG    pitxu        Sending chunks window to be transcribed into the process
# 2026-06-01 08:22:51,515 [MainProcess TranscriptorManager   ] DEBUG    pitxu        Requesting transcription result from the process
# 2026-06-01 08:22:51,515 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ 👁️‍🗨️ Transcription state updated to REQUESTED_TRANSCRIPTION, Now waiting for the Process to answer.
# 2026-06-01 08:22:51,516 [Support     MainThread            ] DEBUG    pitxu        💾 Dumped audio [68266 bytes] of [int16] at [16000 Hz] to file: storage/audio/preprocessed_input/audio_2026-06-01-08-22-51-514475.wav
# 2026-06-01 08:22:51,522 [Support     MainThread            ] DEBUG    matplotlib.pyplot Loaded backend Agg version v2.2.
# 2026-06-01 08:22:51,739 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-01 08:22:51,739 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        ⏳ Waiting for an user interaction. 95% (paused 3s) time left.
# 2026-06-01 08:22:51,739 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🚥 Showing interaction holding percentage 95% on background display
# 2026-06-01 08:22:51,750 [DsiLcd      MainThread            ] INFO     pitxu        🚥 Showing interaction holding percentage 95% on DSI LCD
# 2026-06-01 08:22:52,255 [FasterWhisperStream MainThread            ] DEBUG    pitxu        ----------------------------------------------------------------
# 2026-06-01 08:22:52,256 [FasterWhisperStream MainThread            ] DEBUG    pitxu        |                        Segments info                         |
# 2026-06-01 08:22:52,256 [FasterWhisperStream MainThread            ] DEBUG    pitxu        ----------------------------------------------------------------
# 2026-06-01 08:22:52,256 [FasterWhisperStream MainThread            ] DEBUG    pitxu        |  Good morning.: start: 0.0 (0.0), end: 0.6 (0.6), prob: -0.7 |
# 2026-06-01 08:22:52,256 [FasterWhisperStream MainThread            ] DEBUG    pitxu        ----------------------------------------------------------------
# 2026-06-01 08:22:52,257 [FasterWhisperStream MainThread            ] DEBUG    pitxu        -----------------------------------------------------------
# 2026-06-01 08:22:52,257 [FasterWhisperStream MainThread            ] DEBUG    pitxu        |                        Words info                       |
# 2026-06-01 08:22:52,257 [FasterWhisperStream MainThread            ] DEBUG    pitxu        -----------------------------------------------------------
# 2026-06-01 08:22:52,257 [FasterWhisperStream MainThread            ] DEBUG    pitxu        |  Good    : start: 0.0 (0.0), end: 0.3 (0.3), prob: 0.48 |
# 2026-06-01 08:22:52,258 [FasterWhisperStream MainThread            ] DEBUG    pitxu        |  morning.: start: 0.3 (0.3), end: 0.6 (0.6), prob: 0.89 |
# 2026-06-01 08:22:52,258 [FasterWhisperStream MainThread            ] DEBUG    pitxu        -----------------------------------------------------------
# 2026-06-01 08:22:52,258 [FasterWhisperStream MainThread            ] DEBUG    pitxu        ✏️ Current ongoing transcription: 

# Good morning.

# 2026-06-01 08:22:52,258 [FasterWhisperStream MainThread            ] DEBUG    pitxu        ✏️ Current committed transcription: 



# 2026-06-01 08:22:52,259 [FasterWhisperStream MainThread            ] DEBUG    pitxu        Xprocess [FasterWhisperStream] run() received a [TRANSCRIBE_CHUNK_WINDOW: <class 'list'>]
# 2026-06-01 08:22:52,259 [FasterWhisperStream MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 29 audio chunks with the context of the last overlap and the ongoing transcription.
# 2026-06-01 08:22:52,268 [FasterWhisperStream MainThread            ] DEBUG    pitxu        FasterWhisper Stream: Processing 29 audio chunks with a total of 17899 samples, with an overlap of 8000 samples from the previous chunk.
# 2026-06-01 08:22:52,268 [FasterWhisperStream MainThread            ] INFO     faster_whisper Processing audio with duration 00:01.119
# 2026-06-01 08:22:52,739 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🎤 Speech-to-Text is processing, pausing interaction holding time counter.
# 2026-06-01 08:22:52,739 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        ⏳ Waiting for an user interaction. 95% (paused 4s) time left.
# 2026-06-01 08:22:52,739 [MainProcess ThreadPoolExecutor-0_0] DEBUG    pitxu        🚥 Showing interaction holding percentage 95% on background display
# 2026-06-01 08:22:52,745 [DsiLcd      MainThread            ] INFO     pitxu        🚥 Showing interaction holding percentage 95% on DSI LCD
# 2026-06-01 08:22:53,442 [FasterWhisperStream MainThread            ] DEBUG    pitxu        -------------------------------------------------------------------
# 2026-06-01 08:22:53,442 [FasterWhisperStream MainThread            ] DEBUG    pitxu        |                          Segments info                          |
# 2026-06-01 08:22:53,443 [FasterWhisperStream MainThread            ] DEBUG    pitxu        -------------------------------------------------------------------
# 2026-06-01 08:22:53,443 [FasterWhisperStream MainThread            ] DEBUG    pitxu        |  Good morning.: start: 0.0 (0.6), end: 1.08 (1.68), prob: -0.71 |
# 2026-06-01 08:22:53,443 [FasterWhisperStream MainThread            ] DEBUG    pitxu        -------------------------------------------------------------------
# 2026-06-01 08:22:53,444 [FasterWhisperStream MainThread            ] DEBUG    pitxu        ---------------------------------------------------------------
# 2026-06-01 08:22:53,444 [FasterWhisperStream MainThread            ] DEBUG    pitxu        |                          Words info                         |
# 2026-06-01 08:22:53,444 [FasterWhisperStream MainThread            ] DEBUG    pitxu        ---------------------------------------------------------------
# 2026-06-01 08:22:53,444 [FasterWhisperStream MainThread            ] DEBUG    pitxu        |  Good    : start: 0.0 (0.6), end: 1.08 (1.68), prob: 0.0    |
# 2026-06-01 08:22:53,445 [FasterWhisperStream MainThread            ] DEBUG    pitxu        |  morning.: start: 1.08 (1.68), end: 1.08 (1.68), prob: 0.04 |
# 2026-06-01 08:22:53,445 [FasterWhisperStream MainThread            ] DEBUG    pitxu        ---------------------------------------------------------------
# 2026-06-01 08:22:53,445 [FasterWhisperStream MainThread            ] DEBUG    pitxu        ✏️ Current ongoing transcription: 

# Good morning. Good morning.

# 2026-06-01 08:22:53,445 [FasterWhisperStream MainThread            ] DEBUG    pitxu        ✏️ Current committed transcription: 



# 2026-06-01 08:22:53,446 [FasterWhisperStream MainThread            ] DEBUG    pitxu        Xprocess [FasterWhisperStream] run() received a [RETRIEVE_TRANSCRIPTION_RESULT]
# 2026-06-01 08:22:53,446 [FasterWhisperStream MainThread            ] DEBUG    pitxu        ✏️ Final transcription: 

# Good morning. Good morning.

# 2026-06-01 08:22:53,447 [FasterWhisperStream MainThread            ] DEBUG    pitxu        Final transcription put in the output queue.
# 2026-06-01 08:22:53,493 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ 👁️‍🗨️ Transcription state updated to FINAL_TRANSCRIPTION, it arribed through the transcription result queue.
# 2026-06-01 08:22:53,494 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Got transcription result from the Process: Good morning. Good morning.
# 2026-06-01 08:22:53,494 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Merging transcription result with the final transcription.
# 2026-06-01 08:22:53,494 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ 👁️‍🗨️ Transcription state updated from final_transcription to DONE, Triggering Main callback.
# 2026-06-01 08:22:53,494 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ Triggering on_transcription_finished_callback callback after receiving transcription result from the Process.
# 2026-06-01 08:22:53,494 [MainProcess TranscriptorManager   ] DEBUG    pitxu        ✏️ 👁️‍🗨️ Transcription state updated from done to IDLE, ready for next transcription.
# 2026-06-01 08:22:53,494 [MainProcess MainThread            ] INFO     pitxu        Main execution triggered by user finishing speaking, via Transcription callback.
# 2026-06-01 08:22:53,494 [MainProcess MainThread            ] DEBUG    pitxu        🔇 Stopping the input stream as microphone is muting.
# 2026-06-01 08:22:53,601 [MainProcess MainThread            ] DEBUG    pitxu        🔇 Muting the microphone. Now mute is [True]
# 2026-06-01 08:22:53,601 [MainProcess MainThread            ] DEBUG    pitxu        Getting transcription from STT after VAD detected speech finished, for streaming engine...
# 2026-06-01 08:22:53,601 [MainProcess MainThread            ] DEBUG    pitxu        💬 Recognised dictate: Good morning. Good morning.
# 2026-06-01 08:22:53,601 [MainProcess MainThread            ] DEBUG    pitxu        ⏱️  Dictate 0: 0.0001
# 2026-06-01 08:22:53,601 [MainProcess MainThread            ] DEBUG    pitxu        Checking if text has exit intention: 'Good morning. Good morning.' -> 'good morning good morning': False
# 2026-06-01 08:22:53,601 [MainProcess MainThread            ] DEBUG    pitxu        Detection: Text intends to trigger or continue an interaction.
# 2026-06-01 08:22:53,601 [MainProcess MainThread            ] DEBUG    pitxu        💤  Setting idle mode off.
# 2026-06-01 08:22:53,601 [MainProcess MainThread            ] DEBUG    pitxu        🤖 Triggering thinking interaction on background display.
# 2026-06-01 08:22:53,601 [MainProcess MainThread            ] DEBUG    pitxu        Waiting for queue dsi_lcd_queue to empty. Has now: 1 elements.
# 2026-06-01 08:22:53,607 [DsiLcd      MainThread            ] INFO     pitxu        🤖 Showing KITT thinking on DSI LCD.
# 2026-06-01 08:22:53,619 [DsiLcd      MainThread            ] INFO     pitxu        👀 Showing arbitrary text on DSI LCD while thinking.
# 2026-06-01 08:22:54,106 [MainProcess MainThread            ] DEBUG    pitxu        The queue dsi_lcd_queue is empty now. I've sleept 0.5s.
# 2026-06-01 08:22:54,106 [MainProcess MainThread            ] DEBUG    pitxu        🤖 Setting Chatbot as busy.
# 2026-06-01 08:22:54,107 [MainProcess MainThread            ] INFO     pitxu        ❓ Question in Chatbot: 

# >> Good morning. Good morning.



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
