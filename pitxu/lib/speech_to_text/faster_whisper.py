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
    """
    STT with Faster Whisper.

    - Works
    - Processes all the audio queue in one shot after VAD detects the end of the speech.
    - Slow user feeling.
    - Very accurate, awesome.
    - Being used in the RPi 5 since 2026-05-17
    """

    _model: WhisperModel = None
    _queue: queue.Queue = None
    _preprocessor: Preprocessor = None
    _support: Support = None
    _shared_memory: SharedMemoryManager = None

    is_active: bool = False
    language: str = "en"

    VERBOSE_DEBUG: bool = False

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

                logging_parts.append(("Model from config", model))
                logging_parts.append(("Device for Faster Whisper", device))
                logging_parts.append(("Download root", download_root))
                logging_parts.append(("Compute type", compute_type))
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
        self._support = self._xparams.get("support")
        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory_flags()

        # Keeping track that Whisper is active
        self.is_active = True

        self.log_summary("Faster Whisper Initialization", logging_parts)
    
    def get_queue(self) -> queue.Queue:
        return self._queue
    
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