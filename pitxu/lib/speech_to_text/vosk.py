import queue
import logging
import sys
import json

from pyxavi import Dictionary, Config, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.speech_to_text.preprocess.preprocessor import Preprocessor
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from definitions import SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY

from vosk import Model, KaldiRecognizer, SetLogLevel
import sounddevice as sd

class VoskException(Exception):
    pass

class Vosk(PyXavi):

    ENGLISH: str = "en-us"
    CATALAN: str = "ca"
    GERMAN: str = "de"
    SPANISH: str = "es"

    _model: Model = None
    _queue: queue.Queue = None
    _recognizer: KaldiRecognizer = None
    _preprocessor: Preprocessor = None

    _shared_memory: SharedMemoryManager = None

    device = None
    samplerate = None

    is_active: bool = False

    VERBOSE_DEBUG: bool = True
    VOICE_LIB_LOG_LEVEL: int = 0

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Vosk, self).init_pyxavi(config=config, params=params)

        self.initialize()
    
    def initialize(self):

        self._xlog.info("Initializing Vosk STT")
        logging_parts = []

        language = self._xparams.get("language")
        logging_parts.append(("Language", language))

        if self._xconfig.get("speech-to-text.mock", True):
            self._xlog.info("Mocking Speech-to-Text by Config. Model not loaded.")
        else:
            # Set the log levels for the Gemini API client and httpcore libraries based on the configuration
            self.VOICE_LIB_LOG_LEVEL = self._xconfig.get("libs_logger.vosk.loglevel", self.VOICE_LIB_LOG_LEVEL)
            self._log_debug("Setting Vosk client log level to: " + str(self.VOICE_LIB_LOG_LEVEL))
            SetLogLevel(self.VOICE_LIB_LOG_LEVEL)

            model = self._xconfig.get("speech-to-text.vosk.model." + language, None)
            if model is not None:
                logging_parts.append(("Model from config", model))
                self._model = Model(model_name=model)
            else:
                logging_parts.append(("Model default for language", language))
                self._model = Model(lang=language)

            # We need to be able to receive a samplerate param so that the Server instance can operate a lower samplerate if needed,
            # otherwise it will be forced to use the one from the microphone input, that has nothing to do with the external clients.
            if self._xparams.get("samplerate", None) is not None:
                self.samplerate = self._xparams.get("samplerate")
                logging_parts.append(("Sample rate from params", self.samplerate))

            elif self._xconfig.get("speech-to-text.vosk.input_samplerate", None) is not None and \
                    self._xconfig.get("speech-to-text.vosk.input_samplerate", None) > 0:
                self.samplerate = self._xconfig.get("speech-to-text.vosk.input_samplerate")
                logging_parts.append(("Sample rate from config", self.samplerate))

            else:
                self.samplerate = self._get_samplerate()
                logging_parts.append(("Sample rate from device", self.samplerate))
            
            self.device = self._xconfig.get("speech-to-text.input_device", None)
            logging_parts.append(("Input device", self.device))

            self._log_debug("Vosk: initializing KaldiRecognizer")
            self._recognizer = KaldiRecognizer(self._model, self.samplerate)

        self._queue = queue.Queue()

        self._preprocessor = Preprocessor(config=self._xconfig, params=Dictionary({
            # "samplerate": self._xparams.get("samplerate", self.samplerate)
            "samplerate": self.samplerate
        }))

        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory_flags()

        # Keeping track that Vosk is active
        self.is_active = True

        self.log_summary("Vosk Initialization", logging_parts)
    
    def get_queue(self) -> queue.Queue:
        return self._queue
    
    def recognize(self) -> str:
        try:
            if self._xconfig.get("speech-to-text.mock", True):
                return input("Type your question: [\"exit\" to leave]: \n")
            elif self.is_active == False:
                raise VoskException("Vosk is not active, cannot recognize audio")
            elif self.is_active and self._queue is not None:

                # self._log_debug("Vosk: Recognize called, processing audio chunk from the queue")
                
                # Get from the queue. Only happens if mic is on and allowed
                # If we use block=True, it waits until it receives something.
                if self._queue.empty():
                    return None
                else:
                    data = self._queue.get(block=False)

                    # What about resampling whatever we receive to 16kHz?
                    # Take a look at librosa.resample()

                    # `None` is the marker for end of speech,
                    #   sent by the CaptureHandler when the VAD detects the end of speech.
                    # if data is None:
                    #     # Reset the audio buffers used for plotting,
                    #     #   and do do the actual plotting.
                    #     self._preprocessor.on_speech_end()

                    #     # Oh! side effect! Check if we can actually get the Vosk final result!
                    #     #recognize_final_outcome = self.process_remaining_vosk()
                    #     #self.reset_result()

                # Remember: we use `None` as a marker, so protect against it!
                if data is not None:

                    # Process all chunks that we receive.
                    # recognize_outcome = self.process_audio_chunk(data)

                    # Preprocess. Is it a valid chunk?
                    preprocessed_data = self._preprocessor.preprocess_chunk(data)
                    if preprocessed_data is not None:
                        recognize_outcome = self.process_audio_chunk(preprocessed_data)
                        # If the chunk was identified as human voice in the preprocessor but no transcription was obtained,
                        #   means that we failed in the preprocessing (most likely energy too high).
                        #   Therefore, we add its energy to the average, hoping that this feedback loop
                        #   improves the peak identification in further chunk analysis iteration.
                        # if (recognize_outcome.get("partial") is None or recognize_outcome.get("partial") == "") and \
                        #     recognize_outcome.get("result") is None and \
                        #     recognize_outcome.get("final") is None:
                        #         self._preprocessor.add_untranscripted_audio_energy_to_average(preprocessed_data)
                        # else:
                        #     dd(recognize_outcome)
                    else:
                        recognize_outcome = {
                            "result": None,
                            "partial": None,
                            "final": None
                        }

                    # recognize_final_outcome = self.process_remaining_vosk()
                    # if recognize_final_outcome is not None and "final" in recognize_final_outcome and recognize_final_outcome["final"] is not None:
                    #     recognize_outcome["final"] = recognize_final_outcome["final"]

                    # dd(recognize_outcome)

                    # Since Vosk can return both partial and final results, for normal "local" Pitxu
                    #   we completely ignore the partial.
                    if recognize_outcome.get("result") is not None:
                        result = recognize_outcome.get("result")
                        # if recognize_outcome.get("final") is not None and len(recognize_outcome.get("final")) > 0:
                        #     result = result + " " + recognize_outcome.get("final")

                        # Because we have already a result, regardless of being at the end of the processing queue,
                        #   we perform the reset / cleanup operations before returning.
                        # self._preprocessor.on_speech_end()
                        # self.reset_result()
                        return result
                    # elif recognize_outcome.get("partial") is not None and recognize_outcome.get("partial") != "":
                    #     self._log_debug(f"Vosk: partial is {recognize_outcome.get("partial")}")

                # `None` is the marker for end of speech,
                #   sent by the CaptureHandler when the VAD detects the end of speech.
                # Even we didn't recognise anything, take it as a signal that the speech has ended,
                #   so we can reset the preprocessor and the Vosk buffers for the next transcription.
                else:
                    # Reset the audio buffers used for plotting,
                    #   and do do the actual plotting.
                    self._preprocessor.on_speech_end()

                    # Oh! side effect! Check if we can actually get the Vosk final result!
                    recognize_outcome = self.process_remaining_vosk()
                    result = recognize_outcome.get("result")
                    if recognize_outcome.get("final") is not None and len(recognize_outcome.get("final")) > 0:
                        if result is not None:
                            result = result + " " + recognize_outcome.get("final")
                        else:
                            result = recognize_outcome.get("final")
                    if result is not None and result != "":
                        return result
                    self.reset_result()

        except queue.ShutDown as e:
            self.is_active = False
            raise VoskException("Queue Shutdown detected in Vosk recognize(): " + str(e))
        except VoskException as ve:
            self.is_active = False
            # It's handled in Main, don't even log it here
            raise ve
        except KeyboardInterrupt:
            self._xlog.debug("Pressed Control + C while running Vosk transcription.")
            self.is_active = False
            self.close()
        except BrokenPipeError as bpe:
            self.is_active = False
            raise VoskException("Vosk BrokenPipeError: " + str(bpe))
        except Exception as e:
            self._xlog.error("🛑 Error during Vosk recognition: " + str(e))
            self._xlog.error(full_stack())
            self.close()
            return None
    
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
        self._recognizer.Reset()

    def _get_samplerate(self) -> int:
        device_info = sd.query_devices(self.device, "input")
        # soundfile expects an int, sounddevice provides a float:
        return int(device_info["default_samplerate"])

    def callback(self, indata, frames, time, status):
        """
        This is called (from a separate thread) for each audio block.
        Audio blocks are sentences.

        NOT USED. See CaptureHandler.
        """
        if status:
            self._xlog.debug(f"Vosk callback: Audio input status: {status}")
            print(status, file=sys.stderr)

        if not self.should_skip_audio_input() and self._queue is not None:
            # self._xlog.debug(f"Vosk callback: Received audio block of {len(indata)} bytes, putting it in the queue for processing")
            # print(time.inputBufferAdcTime)
            self._queue.put(bytes(indata))
        # else:
        #     self._xlog.debug("Vosk callback: Skipping audio input, as the microphone is muted or the speaker is busy according to the shared memory flags")
    
    def should_skip_audio_input(self):
        '''
        Checks if the microphone is muted by reading AND if the speaker is talking via the shared memory flags
        '''

        speaker_is_busy = False
        mic_is_muted = False

        if self._shared_memory is None:
            self._xlog.error("Shared Memory is None, cannot read 'SHARED_MICROPHONE_MUTED' flag")
            return False
        if (not isinstance(self._shared_memory.read_shared_memory_flag(SHARED_MICROPHONE_MUTED), bool)):
            self._xlog.error("Shared Memory flag 3 should be 'SHARED_MICROPHONE_MUTED' but is not a boolean" + str(self._shared_memory.read_shared_memory_flag(SHARED_MICROPHONE_MUTED)))
            return False
        if (not isinstance(self._shared_memory.read_shared_memory_flag(SHARED_SPEAKER_BUSY), bool)):
            self._xlog.error("Shared Memory flag 4 should be 'SHARED_SPEAKER_BUSY' but is not a boolean" + str(self._shared_memory.read_shared_memory_flag(SHARED_SPEAKER_BUSY)))
            return False
        mic_is_muted = self._shared_memory.read_shared_memory_flag(SHARED_MICROPHONE_MUTED)
        speaker_is_busy = self._shared_memory.read_shared_memory_flag(SHARED_SPEAKER_BUSY)

        return mic_is_muted or speaker_is_busy

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
        
        # Remember that Vosk is not active anymore
        self.is_active = False

        self._xlog.info("Vosk STT closed")


        
