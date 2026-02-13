import logging, time
import numpy as np
import sounddevice
from piper.voice import PiperVoice

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction
from definitions import ROOT_DIR, SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY

class Piper(Xprocess):

    MODELS_PATH = "tts_models/"

    _model = None
    _voice: PiperVoice = None
    _output_stream: sounddevice.OutputStream = None

    PIPER_LIB_LOG_LEVEL: int = logging.INFO

    def get_process_name(self) -> str:
        return "Piper"

    def initialize(self):
        self._xlog.info("Initializing Piper Worker")
        language = self._xparams.get("language")
        self._log_debug("Language is: " + str(language))
        model_name = self._xconfig.get("text-to-speech.per_language." + language)
        self._model = ROOT_DIR + "/" + str(self._xconfig.get("storage.path")) + str(self.MODELS_PATH) + str(model_name) + ".onnx"
        self._xlog.info("Loading TTS model from: " + self._model)
        self._voice = PiperVoice.load(self._model)

        # Set the log levels for the Piper libraries based on the configuration
        self.PIPER_LIB_LOG_LEVEL = self._xconfig.get("libs_logger.piper.loglevel", self.PIPER_LIB_LOG_LEVEL)
        self._log_debug("Setting Piper client log level to: " + str(self.PIPER_LIB_LOG_LEVEL))
        logging.getLogger("piper.voice").setLevel(self.PIPER_LIB_LOG_LEVEL)

        self._log_debug("Creating Piper Output Stream with samplerate: " + str(self._voice.config.sample_rate))
        self._output_stream = sounddevice.OutputStream(
            samplerate=self._voice.config.sample_rate,
            blocksize=0,
            channels=1,
            dtype='int16'
        )
        # if self._xconfig.get("text-to-speech.mock", True) is False:
        #     self._xlog.info("Creating Real Piper Output Stream")
        #     self._output_stream = sounddevice.OutputStream(
        #         samplerate=self._voice.config.sample_rate,
        #         blocksize=0,
        #         channels=1,
        #         dtype='int16'
        #     )
        # else:
        #     from pitxu.lib.text_to_speech.mocked_output_stream import MockedOutputStream
        #     self._xlog.info("Creating Mocked Piper Output Stream")
        #     self._output_stream = MockedOutputStream(config=self._xconfig, dictionary=self._xparams)
        
        # self._output_stream = sounddevice.OutputStream(
        #         samplerate=self._voice.config.sample_rate,
        #         blocksize=0,
        #         channels=1,
        #         dtype='int16'
        #     )

    def finish(self):
        self._xlog.debug("Closing output stream")
        if self._output_stream is not None:
            self._output_stream.close()
        self._xlog.debug("Done finishing Piper Worker")
    
    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        
        if action == XprocAction.SAY and param != "":
            self.say(param)
        
        if action == XprocAction.SAY_OUTPUT_QUEUE and param != "":
            self.synthesize_and_return_through_output_queue(param)

    def say(self, text: str):

        # While talking we set the speaker busy flag and mute the microphone, keeping track of its previous state
        # So that we can restore it to what it was before
        # REMOVEME: This is now handled in the parent Xprocess
        # self.write_shared_memory_flag(SHARED_SPEAKER_BUSY, True)

        if self._xconfig.get("text-to-speech.mock", True):
            self._xlog.warning("Mocking TTS by Config. Should have said [" + text + "]")
            # Emulate that we're doing something by waiting a second per 10 words
            words = text.split(" ")
            wait_time = max(1, len(words) / 10)
            self._xlog.debug(f"Mocking TTS wait time for {wait_time} seconds")
            time.sleep(wait_time)

        else:
            self._xlog.debug("Saying [" + text.replace("\n", "\\n") + "]")

            self._output_stream.start()
            # with self._output_stream:
            self._log_debug("Output stream started")

            # According to the docs, PiperVoice.synthesize returns an iterator of AudioChunks
            # which represent sentences.
            for int_data in self.generate_audio_chunks(text):
                # if self.interrupt_event.is_set():
                #     self.get_logger().info("Speech interrupted.")
                #     break

                # Make it to speak
                self._log_debug("Writing audio bytes to output stream")
                self._output_stream.write(int_data)

            self._log_debug("All audio chunks processed, stopping output stream")
            # Comment the following and tab properly for the with statement if used
            self._output_stream.stop()
        
        self._log_debug("Finished saying communication")
    
    def synthesize_and_return_through_output_queue(self, text: str):
        if self._output_queue is not None:
            self._log_debug("Generating audio bytes for text and sending through output queue")
            # Generate the audio bytes for the given text and send them through the output queue
            for audio_bytes in self.generate_audio_chunks(text):
                self._output_queue.put({
                    "audio_bytes": audio_bytes,
                    "sample_rate": self._voice.config.sample_rate
                })
            # We need to tell the consumer that we're done sending audio bytes,
            # so we send a None value (which is not a valid audio chunk)
            self._output_queue.put(self._sentinel_output_queue)
        else:
            self._log_debug("No output queue defined, cannot send audio bytes")
    
    def generate_audio_chunks(self, text: str):
        # This is a generator that yields audio chunks for the given text, to be used in streaming scenarios
        for chunk in self._voice.synthesize(text):
            int_data = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
            yield int_data
    
    # REMOVEME: This is now handled in the parent Xprocess
    # def pause_mic(self):
    #     self.write_shared_memory_flag(SHARED_MICROPHONE_MUTED, True)
    # REMOVEME: This is now handled in the parent Xprocess
    # def resume_mic(self):
    #     self.write_shared_memory_flag(SHARED_MICROPHONE_MUTED, False)
