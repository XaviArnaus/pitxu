import logging, time
import numpy as np
import sounddevice
from piper.voice import PiperVoice

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction
from definitions import ROOT_DIR, SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY
from pitxu.lib.utils.amplitude import Amplitude

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
            for chunk in self._voice.synthesize(text):
                # if self.interrupt_event.is_set():
                #     self.get_logger().info("Speech interrupted.")
                #     break
                self._log_debug("Processing audio chunk of size: " + str(len(chunk.audio_int16_bytes)) + " bytes")
                int_data = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)

                # Make it to speak
                self._log_debug("Writing audio chunk to output stream")
                self._output_stream.write(int_data)

            self._log_debug("All audio chunks processed, stopping output stream")
            # Comment the following and tab properly for the with statement if used
            self._output_stream.stop()
        
        self._log_debug("Finished saying communication")
            
        # Restore the speaker and microphone states
        # REMOVEME: This is now handled in the parent Xprocess
        # self.write_shared_memory_flag(SHARED_SPEAKER_BUSY, False)
        # self._log_debug("Restore the speaker busy flag to False after finishing saying")
    
    def pause_mic(self):
        self.write_shared_memory_flag(SHARED_MICROPHONE_MUTED, True)

    def resume_mic(self):
        self.write_shared_memory_flag(SHARED_MICROPHONE_MUTED, False)

# 2026-01-14 22:47:15,506 [Piper-4     ] DEBUG    oscar        Initializing SharedMemoryManager
# 2026-01-14 22:47:15,506 [Piper-4     ] INFO     oscar        Loading flags from Shared Memory
# 2026-01-14 22:47:15,506 [Piper-4     ] INFO     oscar        Loading VU meter from Shared Memory
# 2026-01-14 22:47:15,507 [Piper-4     ] DEBUG    oscar        Xprocess [Piper] run()
# 2026-01-14 22:47:15,507 [Piper-4     ] DEBUG    oscar        Xprocess [Piper] run() received a [INITIALIZE]
# 2026-01-14 22:47:15,507 [Piper-4     ] INFO     oscar        Initializing Piper Worker
# 2026-01-14 22:47:15,510 [Piper-4     ] DEBUG    piper.voice  Guessing voice config path: /home/xavier/pitxu/storage/tts_models/ca_ES-upc_pau-x_low.onnx.json
# 2026-01-14 22:47:16,899 [Piper-4     ] DEBUG    oscar        Creating Piper Output Stream with samplerate: 16000
# Resume failed, couldn't restore original sample settings.
# 2026-01-14 22:47:16,904 [Piper-4     ] DEBUG    oscar        Xprocess [Piper] run() received a [SAY: Hola]
# 2026-01-14 22:47:16,904 [Piper-4     ] DEBUG    oscar        Saying [Hola]
# Resume failed, couldn't restore original sample settings.
# Resume failed, couldn't restore original sample settings.
# Resume failed, couldn't restore original sample settings.
# 2026-01-14 22:47:16,907 [Piper-4     ] DEBUG    oscar        Output stream started
# Resume failed, couldn't restore original sample settings.
# Resume failed, couldn't restore original sample settings.
# Resume failed, couldn't restore original sample settings.
# Resume failed, couldn't restore original sample settings.
# 2026-01-14 22:47:16,916 [MatrixLed-3 ] DEBUG    oscar        Xprocess [Matrix] run() received a [SAY: Hola]
# 2026-01-14 22:47:16,916 [MatrixLed-3 ] INFO     oscar        👄 Showing KITT mouth on Matrix LED.
# 2026-01-14 22:47:16,916 [MatrixLed-3 ] DEBUG    oscar        Opening Handable Canvas
# 2026-01-14 22:47:16,916 [MainProcess ] DEBUG    oscar        Waiting for queue speaker_queue to empty. Has now: 0 elements.
# 2026-01-14 22:47:16,917 [MainProcess ] DEBUG    oscar        The queue speaker_queue is empty now. I've sleept 0s.
# 2026-01-14 22:47:16,917 [MainProcess ] DEBUG    oscar        Waiting for the process speaker_busy to idle. It's now: BUSY.
# 2026-01-14 22:47:16,917 [MatrixLed-3 ] DEBUG    oscar        Creating Matrix Emulation Handable Canvas
# Resume failed, couldn't restore original sample settings.
# Resume failed, couldn't restore original sample settings.
# Resume failed, couldn't restore original sample settings.
# Resume failed, couldn't restore original sample settings.
# Resume failed, couldn't restore original sample settings.
# Resume failed, couldn't restore original sample settings.
# Resume failed, couldn't restore original sample settings.
