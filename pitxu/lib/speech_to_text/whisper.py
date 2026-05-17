from pyxavi import Dictionary, Config, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.speech_to_text.preprocess.preprocessor import Preprocessor
from pitxu.lib.speech_to_text.speech_to_text import SpeechToTextException
from pitxu.lib.support_process.support import Support
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from definitions import SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY

import queue
import whisper
import os
import numpy as np

class Whisper(PyXavi):

    _model: whisper.Whisper = None
    _queue: queue.Queue = None
    _preprocessor: Preprocessor = None
    _support: Support = None
    _shared_memory: SharedMemoryManager = None

    is_active: bool = False
    language: str = "en"

    VERBOSE_WHISPER_LIB: bool = False
    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Whisper, self).init_pyxavi(config=config, params=params)

        self.initialize()
    
    def initialize(self):

        self._xlog.info("Initializing Whisper STT")
        logging_parts = []

        language = self._xparams.get("language", "en")
        if language == "en-us":
            # I need to correct this Vosk language stupidity that is populated all around the code!!!
            language = "en"
        logging_parts.append(("Language", language))

        if self._xconfig.get("speech-to-text.mock", True):
            self._xlog.info("Mocking Speech-to-Text by Config. Model not loaded.")
        else:
            model = self._xconfig.get("speech-to-text.whisper.model." + language, )
            if model is not None:

                # I don't understand why device and download_root get read as tuples instead of strings.
                device = str(self._xconfig.get("speech-to-text.whisper.device", "cpu"))
                download_root = str(os.path.join(self._xconfig.get("storage.path"), self._xconfig.get("speech-to-text.whisper.download_root", None)))
                in_memory = self._xconfig.get("speech-to-text.whisper.in_memory", True)

                logging_parts.append(("Model from config", model))
                logging_parts.append(("Device for Whisper", device))
                logging_parts.append(("Download root", download_root))
                logging_parts.append(("In memory loading", in_memory))
                self.log_summary("Whisper Model Initialization", logging_parts)

                self._model = whisper.load_model(model,
                                                 device=device,
                                                 download_root=download_root,
                                                 in_memory=in_memory)
            else:
                raise SpeechToTextException(f"No model specified in config for language {language}, and mocking is disabled, cannot initialize Whisper STT.")

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

        self.log_summary("Whisper Initialization", logging_parts)
    
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

                self._log_debug(f"Whisper: Processing all audio chunks [{self._queue.qsize()}] from the queue at once")

                audio_np = []

                # Process all the chunks in the queue until it's empty.
                while not self._queue.empty():

                    # Get the next chunk from the queue.
                    data = self._queue.get()

                    if data is None:
                        self._log_debug("Whisper: Received None data from the queue, skipping it.")
                        continue

                    # Preprocess. Returns a numpy array in INT16 (PCM_16) format.
                    preprocessed_data = self._preprocessor.preprocess_chunk(data, return_in_numpy=True)

                    if preprocessed_data is None:
                        self._log_debug("Whisper: Preprocessed data is None, skipping this chunk.")
                        continue

                    audio_np.append(preprocessed_data)
                
                self._log_debug(f"Whisper: All audio chunks from the queue have been preprocessed, total {len(audio_np)} chunks. Transcribing them with Whisper...")

                if len(audio_np) == 0:
                    self._log_debug("Whisper: No audio chunks to process after preprocessing, returning empty result.")
                    return ""
                # Join the chunks and transcribe them with Whisper.
                #   Note: we don't want to join the chunks before preprocessing, because this could lead to memory issues if the user speaks for a long time, and also because the Preprocessor may do some operations that are better to do on smaller chunks (for example, VAD).
                transcription_data = self._model.transcribe(
                    np.concatenate(audio_np).flatten().astype(np.float32) / 32768.0, 
                    language=self.language,
                    verbose=self.VERBOSE_WHISPER_LIB)
                
                # Extract just the transcription result. Keep in mind that we receive more info, like:
                # {'text': ' Hello?', 'segments': [{'id': 0, 'seek': 0, 'start': 0.0, 'end': 2.0, 'text': ' Hello?', 'tokens': [50363, 18435, 30, 50463], 'temperature': 0.0, 'avg_logprob': -0.8661511421203614, 'compression_ratio': 0.42857142857142855, 'no_speech_prob': 0.01292417012155056}], 'language': 'en'}
                result = transcription_data.get("text", "").strip()

                self._log_debug(f"Whisper: Finished processing all audio chunks from the queue, final result: {result}")
                return result

        except queue.ShutDown as e:
            self.is_active = False
            raise SpeechToTextException("Queue Shutdown detected in Whisper recognize(): " + str(e))
        except SpeechToTextException as ve:
            self.is_active = False
            # It's handled in Main, don't even log it here
            raise ve
        except KeyboardInterrupt:
            self._xlog.debug("Pressed Control + C while running Whisper transcription.")
            self.is_active = False
            self.close()
        except BrokenPipeError as bpe:
            self.is_active = False
            raise SpeechToTextException("Whisper BrokenPipeError: " + str(bpe))
        except Exception as e:
            self._xlog.error("🛑 Error during Whisper recognition: " + str(e))
            self._xlog.error(full_stack())
            self.close()
            return None
    
    def close(self):
        self._xlog.info("Closing Whisper STT")
        
        if self._model is not None:
            self._xlog.debug("Deleting Whisper model")
            del self._model
        
        if self._queue is not None:
            self._xlog.debug("Deleting Whisper queue")
            del self._queue
        
        if self._support is not None:
            self._xlog.debug("Closing Support process from Whisper and deleting it")
            del self._support
        
        # Remember that Whisper is not active anymore
        self.is_active = False

        self._xlog.info("Whisper STT closed")
