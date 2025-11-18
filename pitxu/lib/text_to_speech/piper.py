import logging
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

    def get_process_name(self) -> str:
        return "Piper"

    def initialize(self):
        self._xlog.info("Initializing Piper Worker")
        language = self._xparams.get("language")
        model_name = self._xconfig.get("text-to-speech.per_language." + language)
        self._model = ROOT_DIR + "/" + self._xconfig.get("storage.path") + self.MODELS_PATH + model_name + ".onnx"
        self._voice = PiperVoice.load(self._model)
        self._output_stream = sounddevice.OutputStream(
            samplerate=self._voice.config.sample_rate,
            blocksize=0,
            channels=1,
            dtype='int16',
        )
    
    def finish(self):
        self._xlog.debug("Closing output stream")
        self._output_stream.close()
        self._xlog.debug("Done finishing Piper Worker")
    
    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: str):
        
        if action == XprocAction.SAY and param != "":
            self.say(param)

    def say(self, text: str):

        # While talking we set the speaker busy flag and mute the microphone, keeping track of its previous state
        # So taht we can restore it to what it was before
        # previous_mic_state = self.read_shared_memory_flag(SHARED_MICROPHONE_MUTED)
        # self.write_shared_memory_flag(SHARED_MICROPHONE_MUTED, True)
        self.write_shared_memory_flag(SHARED_SPEAKER_BUSY, True)

        if self._xconfig.get("text-to-speech.mock", True):
            self._xlog.warning("Mocking TTS by Config. Should have said [" + text + "]")
        else:
            self._xlog.debug("Saying [" + text.replace("\n", "\\n") + "]")
            self._output_stream.start()

            for chunk in self._voice.synthesize(text):
                int_data = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
                self._output_stream.write(int_data)

            self._output_stream.stop()
            
        # Restore the speaker and microphone states
        self.write_shared_memory_flag(SHARED_SPEAKER_BUSY, False)
        # self.write_shared_memory_flag(SHARED_MICROPHONE_MUTED, previous_mic_state)
    
    def pause_mic(self):
        self.write_shared_memory_flag(SHARED_MICROPHONE_MUTED, True)

    def resume_mic(self):
        self.write_shared_memory_flag(SHARED_MICROPHONE_MUTED, False)