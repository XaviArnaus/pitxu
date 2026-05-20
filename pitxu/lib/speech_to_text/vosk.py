import queue
import json

from pyxavi import Dictionary, Config, full_stack
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.speech_to_text.preprocess.preprocessor import Preprocessor
from pitxu.lib.speech_to_text.speech_to_text import SpeechToTextException
from pitxu.lib.support_process.support import Support
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from definitions import SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY

from vosk import Model, KaldiRecognizer, SetLogLevel

class Vosk(PyXavi):

    ENGLISH: str = "en"
    CATALAN: str = "ca"
    GERMAN: str = "de"
    SPANISH: str = "es"

    _model: Model = None
    _queue: queue.Queue = None
    _recognizer: KaldiRecognizer = None
    _preprocessor: Preprocessor = None
    _support: Support = None
    _shared_memory: SharedMemoryManager = None

    samplerate = None

    is_active: bool = False

    transcription_result: str = None

    VERBOSE_DEBUG: bool = True
    VOICE_LIB_LOG_LEVEL: int = 0

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Vosk, self).init_pyxavi(config=config, params=params)

        self.initialize()
    
    def _convert_to_vosk_language(self, language: str) -> str:
        # Vosk uses "en-us" for English, but we use "en" in the rest of the code, so we need to convert it.
        if language == "en":
            return "en-us"
        return language
    
    def initialize(self):

        self._xlog.info("Initializing Vosk STT")
        logging_parts = []

        language = self._xparams.get("language")
        logging_parts.append(("Language", language))

        if self._xconfig.get("speech-to-text.mock", True):
            self._xlog.info("Mocking Speech-to-Text by Config. Model not loaded.")
        else:
            # Set the log levels for the Vosk libraries based on the configuration
            self.VOICE_LIB_LOG_LEVEL = self._xconfig.get("libs_logger.vosk.loglevel", self.VOICE_LIB_LOG_LEVEL)
            self._log_debug("Setting Vosk client log level to: " + str(self.VOICE_LIB_LOG_LEVEL))
            SetLogLevel(self.VOICE_LIB_LOG_LEVEL)

            model = self._xconfig.get("speech-to-text.vosk.model." + language, None)
            if model is not None:
                logging_parts.append(("Model from config", model))
                self._model = Model(model_name=model)
            else:
                logging_parts.append(("Model default for language", language))
                logging_parts.append(("vosk language code", self._convert_to_vosk_language(language)))
                self._model = Model(lang=self._convert_to_vosk_language(language))

            # We need to be able to receive a samplerate param so that the Server instance can operate a lower samplerate if needed,
            #   otherwise it will be forced to use the one from the microphone input, that has nothing to do with the external clients.
            # For normal local Pitxu, the chunk is downsampled in the CaptureHandler to 16kHz.
            # The choice is done in the calling:
            #   - For the Server, it is inside the Server initialisation from Main.
            #   - For the local Pitxu, it is inside the Params and Support initialisation from Main.
            #   > Both set a "samplerate" param, which value depends on one or another gathered in AudioParametersLoader.
            self.samplerate = self._xparams.get("samplerate", None)
            logging_parts.append(("Sample rate", self.samplerate))

            # Forwarding the Support process to the Preprocessor via xparams,
            #   here just checking that it's there, for the log summary.
            logging_parts.append(("Support Class is present", "Yes" \
                                  if self._xparams.key_exists("support") \
                                    and self._xparams.get("support") is not None \
                                    and isinstance(self._xparams.get("support"), Support) \
                                  else "No"))

            self._log_debug("Vosk: initializing KaldiRecognizer")
            self._recognizer = KaldiRecognizer(self._model, self.samplerate)

        self._queue = queue.Queue()
        self._preprocessor = Preprocessor(config=self._xconfig, params=self._xparams)
        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory_flags()

        # Keeping track that Vosk is active
        self.is_active = True

        self.log_summary("Vosk Initialization", logging_parts)
    
    def get_queue(self) -> queue.Queue:
        return self._queue
    
    def recognize(self) -> str:
        # TODO: Not used in Main anymore after the Callback-based approach. Check the Client PTT and follow the Server Side processing!!
        try:
            if self._xconfig.get("speech-to-text.mock", True):
                return input("Type your question: [\"exit\" to leave]: \n")
            elif self.is_active == False:
                raise SpeechToTextException("Vosk is not active, cannot recognize audio")
            elif self.is_active and self._queue is not None:

                # self._log_debug("Vosk: Recognize called, processing audio chunk from the queue")
                
                # Get from the queue. Only happens if mic is on and allowed, and VAD detected speech.
                # If we use block=True, it waits until it receives something.
                if self._queue.empty():
                    return None
                else:
                    data = self._queue.get(block=False)

                    # `None` is the marker for end of speech,
                    #   sent by the CaptureHandler when the VAD detects the end of speech.
                    # if data is None:
                    #     # Reset the audio buffers used for plotting,
                    #     #   and do do the actual plotting.
                    #     self._preprocessor.on_speech_end()

                    #     # Oh! side effect! Check if we can actually get the Vosk final result!
                    #     #recognize_final_outcome = self.process_remaining_vosk()
                    #     #self.reset_result()
                
                if self._xconfig.get("speech-to-text.vad.enabled", False):
                    # Process the audio chunck using VAD to identify the end of the speech.
                    return self.process_audio_input_vad(data)
                else:
                    # Process the audio chunk without VAD, so we rely on the CaptureHandler to send us the chunks and the `None` marker at the end of the speech.
                    return self.process_audio_input_without_vad(data)

        except queue.ShutDown as e:
            self.is_active = False
            raise SpeechToTextException("Queue Shutdown detected in Vosk recognize(): " + str(e))
        except SpeechToTextException as ve:
            self.is_active = False
            # It's handled in Main, don't even log it here
            raise ve
        except KeyboardInterrupt:
            self._xlog.debug("Pressed Control + C while running Vosk transcription.")
            self.is_active = False
            self.close()
        except BrokenPipeError as bpe:
            self.is_active = False
            raise SpeechToTextException("Vosk BrokenPipeError: " + str(bpe))
        except Exception as e:
            self._xlog.error("🛑 Error during Vosk recognition: " + str(e))
            self._xlog.error(full_stack())
            self.close()
            return None
    
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
                raise SpeechToTextException("Vosk is not active, cannot recognize audio")
            elif self.is_active and self._queue is not None:

                result = None

                self._log_debug(f"Vosk: Recognize all queue at once called, processing all audio chunks [{self._queue.qsize()}] from the queue")

                # Process all the chunks in the queue until it's empty.
                while not self._queue.empty():

                    # Get the next chunk from the queue.
                    data = self._queue.get()

                    # This method is only useful for VAD processing, so simply rely on the process we know that already works.
                    transcription = self.process_audio_input_vad(data)
                    if transcription is not None and transcription.strip() != "":
                        if result is None:
                            result = transcription.strip()
                        else:
                            self._xlog.warning("Vosk: Multiple transcriptions received in the queue, concatenating results.")
                            result = result + " " + transcription.strip()
                
                self._log_debug(f"Vosk: Finished processing all audio chunks from the queue, final result: {result}")
                return result

        except queue.ShutDown as e:
            self.is_active = False
            raise SpeechToTextException("Queue Shutdown detected in Vosk recognize(): " + str(e))
        except SpeechToTextException as ve:
            self.is_active = False
            # It's handled in Main, don't even log it here
            raise ve
        except KeyboardInterrupt:
            self._xlog.debug("Pressed Control + C while running Vosk transcription.")
            self.is_active = False
            self.close()
        except BrokenPipeError as bpe:
            self.is_active = False
            raise SpeechToTextException("Vosk BrokenPipeError: " + str(bpe))
        except Exception as e:
            self._xlog.error("🛑 Error during Vosk recognition: " + str(e))
            self._xlog.error(full_stack())
            self.close()
            return None
    
    def process_audio_input_without_vad(self, data: bytes):
        # TODO: Not used in Main anymore after the Callback-based approach. Check the Client PTT and follow the Server Side processing!!

        # We have a VAD identifying the end of the speech,
        #   but if apparently gets stuck at the end of the speech, not sending the end of speech marker (`None`) to the queue.

        # Remember: we use `None` as a marker, so protect against it!
        if data is not None:

            # Preprocess. Is it a valid chunk?
            preprocessed_data = self._preprocessor.preprocess_chunk(data)
            if preprocessed_data is not None:
                recognize_outcome = self.process_audio_chunk(preprocessed_data)
            else:
                recognize_outcome = {
                    "result": None,
                    "partial": None,
                    "final": None
                }

            # Since Vosk can return both partial and final results, for normal "local" Pitxu
            #   we completely ignore the partial.
            if recognize_outcome.get("result") is not None:
                self.add_to_transcription_result(recognize_outcome.get("result"))
            
            # If anything gets recognised, stop here and take it as the end of transcription.
            if self.transcription_result is not None and self.transcription_result != "":
                # Check if we can actually get the Vosk final result
                recognize_outcome = self.process_remaining_vosk()
                self.add_to_transcription_result(recognize_outcome.get("result"))
                # Extract all we have from Vosk. It also resets the Vosk buffers, so we are ready for the next transcription.
                if recognize_outcome.get("final") is not None and len(recognize_outcome.get("final")) > 0:
                    self.add_to_transcription_result(recognize_outcome.get("final"))
                # Reset the audio buffers used for plotting, and do do the actual plotting.
                self._preprocessor.on_speech_end()
                # Grab the result, reset the transcription result for the next transcription, and return it.
                result = self.transcription_result
                self.reset_result()
                return result
        
    def process_audio_input_vad(self, data: bytes) -> str | None:

        # Remember: we use `None` as a marker, so protect against it!
        if data is not None:

            # Preprocess. Is it a valid chunk?
            preprocessed_data = self._preprocessor.preprocess_chunk(data)
            if preprocessed_data is not None:
                recognize_outcome = self.process_audio_chunk(preprocessed_data)
            else:
                recognize_outcome = {
                    "result": None,
                    "partial": None,
                    "final": None
                }

            # Since Vosk can return both partial and final results, for normal "local" Pitxu
            #   we completely ignore the partial.
            if recognize_outcome.get("result") is not None:
                self.add_to_transcription_result(recognize_outcome.get("result"))

            # elif recognize_outcome.get("partial") is not None and recognize_outcome.get("partial") != "":
            #     self._log_debug(f"Vosk: partial is {recognize_outcome.get("partial")}")

        # `None` is the marker for end of speech,
        #   sent by the CaptureHandler when the VAD detects the end of speech.
        # Even we didn't recognise anything, take it as a signal that the speech has ended,
        #   so we can reset the preprocessor and the Vosk buffers for the next transcription.
        else:
            self._xlog.debug("Vosk: End of speech detected by VAD, processing final results and resetting buffers")
            # Reset the audio buffers used for plotting, and do do the actual plotting.
            self._preprocessor.on_speech_end()

            # Check if we can actually get the Vosk final result
            recognize_outcome = self.process_remaining_vosk()
            self.add_to_transcription_result(recognize_outcome.get("result"))

            if recognize_outcome.get("final") is not None and len(recognize_outcome.get("final")) > 0:
                self.add_to_transcription_result(recognize_outcome.get("final"))
        
            # Now, we may have a result or we may be at the end of the speech without result.
            if self.transcription_result is not None and self.transcription_result != "":
                result = self.transcription_result
                self.reset_result()
                return result
    
    def add_to_transcription_result(self, text: str):
        if text is None or text.strip() == "":
            self._log_debug("No text to add to transcription result, skipping.")
            return

        self._log_debug(f"Adding text to transcription result: [{text}]")
        if self.transcription_result is None:
            self.transcription_result = text
        else:
            self.transcription_result = self.transcription_result + " " + text
        self._log_debug(f"Current transcription result: [{self.transcription_result}]")
    
    def process_audio_chunk(self, data: bytes) -> dict | None:
        """
        Method to be called to process audio data received from the microphone input or the server endpoint.

        Some notes for my further "me":
        - When silence is detected AcceptWaveform() returns True and you can retrieve the result with Result(). 
            If it returns False you can retrieve a partial result with PartialResult().
            The FinalResult() means the stream is ended, buffers are flushed and you retrieve the remaining result which could be silence.
        - This means that we CAN NOT use FinalResult() unless we know that we don't receive more audio (for example, with PTT),
            otherwise Vosk flushes the buffers and we end up not receiving any result.
        - Proof: I added the FinalResult() included in the loop for AcceptWaveform(), and Vosk only worked for the PTT client. The normal
            local Pitxu stopped working because Vosk was flushing the buffers every time it received a chunk of audio.

        """
        outcome = {
            "result": None,
            "partial": None,
            "final": None
        }
        if self._recognizer.AcceptWaveform(data):
            result = json.loads(self._recognizer.Result())
            result_text = str(result["text"]).replace("\n", "").strip()
            if result_text == "":
                outcome["result"] = None
            else:
                self._xlog.debug(f"Vosk: Recognized text: [{result_text}]")
                outcome["result"] = result_text

            # DO NOT USE FinalResult() UNLESS YOU KNOW FOR SURE THAT THE STREAM HAS ENDED.
            #   It flushes the other detected chunks!
            # final_result = self._recognizer.FinalResult()
            # ...
            
        else:
            result = json.loads(self._recognizer.PartialResult())
            outcome["partial"] = str(result["partial"]).replace("\n", "").strip()

        return outcome
    
    def process_remaining_vosk(self) -> str | None:
        outcome = {
            "result": None,
            "partial": None,
            "final": None
        }
        final_result = self._recognizer.FinalResult()
        if final_result:
            result = json.loads(final_result)
            result_text = str(result["text"]).replace("\n", "").strip()
            if result_text == "":
                outcome["final"] = None
            else:
                self._xlog.debug(f"Vosk: Final recognized text: [{result_text}]")
                outcome["final"] = result_text
        return outcome
    
    def reset_result(self):
        """
        Method to reset the Vosk recognizer result. This is needed to avoid having old transcriptions in the next calls.
        It is used in the server endpoint after processing a transcription, to clean the Vosk state for the next transcription.
        """
        self.transcription_result = None
        self._recognizer.Reset()

    def close(self):
        self._xlog.info("Closing Vosk STT")

        if self._recognizer is not None:
            self._xlog.debug("Deleting Vosk recognizer")
            del self._recognizer
        
        if self._model is not None:
            self._xlog.debug("Deleting Vosk model")
            del self._model
        
        if self._queue is not None:
            self._xlog.debug("Deleting Vosk queue")
            del self._queue
        
        if self._support is not None:
            self._xlog.debug("Closing Support process from Vosk")
            del self._support
        
        # Remember that Vosk is not active anymore
        self.is_active = False

        self._xlog.info("Vosk STT closed")


        
