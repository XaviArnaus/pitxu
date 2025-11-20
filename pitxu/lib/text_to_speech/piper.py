import logging
import numpy as np
import sounddevice
from piper.voice import PiperVoice

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction
from definitions import ROOT_DIR, SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY,\
    SHARED_VU_COL_1, SHARED_VU_COL_2, SHARED_VU_COL_3, SHARED_VU_COL_4
from pitxu.lib.utils.amplitude import Amplitude

class Piper(Xprocess):

    MODELS_PATH = "tts_models/"

    _model = None
    _voice: PiperVoice = None
    _output_stream: sounddevice.OutputStream = None

    _maximal_amplitude: Amplitude = Amplitude()

    VU_METER_SCALE = 4

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
                
                # Update VU Meter columns in shared memory
                # audio_data = self._output_stream.read(len(int_data))[0]
                self._xlog.debug("Calculating amplitude for VU Meter for: " + str(len(int_data.tobytes())) + " bytes of audio data")
                amplitude = Amplitude.from_data(int_data.tobytes())
                if amplitude > self._maximal_amplitude:
                    self._maximal_amplitude = amplitude

                # Column 1: It's the LED column 0 and 7. Max scale: 1.
                # amp_col_1, maximal_amp_col_1, delta_1 = amplitude.get_values(scale=1 * self.VU_METER_SCALE, maximal=self._maximal_amplitude)
                # self.write_shared_memory_vu_meter_column(SHARED_VU_COL_1, amp_col_1)
                # Column 2: It's the LED column 1 and 6. Max scale: 2.
                amp_col_2, maximal_amp_col_2, delta_2 = amplitude.get_values(scale=2 * self.VU_METER_SCALE, maximal=self._maximal_amplitude)
                self.write_shared_memory_vu_meter_column(SHARED_VU_COL_2, amp_col_2)
                # Column 3: It's the LED column 2 and 5. Max scale: 3.
                amp_col_3, maximal_amp_col_3, delta_3 = amplitude.get_values(scale=3 * self.VU_METER_SCALE, maximal=self._maximal_amplitude)
                self.write_shared_memory_vu_meter_column(SHARED_VU_COL_3, amp_col_3)
                # Column 4: It's the LED column 3 and 4. Max scale: 4.
                amp_col_4, maximal_amp_col_4, delta_4 = amplitude.get_values(scale=4 * self.VU_METER_SCALE, maximal=self._maximal_amplitude)
                self.write_shared_memory_vu_meter_column(SHARED_VU_COL_4, amp_col_4)
                # self._xlog.debug(f"📶 Amplitude: {amplitude.to_int(self.VU_METER_SCALE)} | VU Meter Columns: 1:{amp_col_1} 2:{amp_col_2} 3:{amp_col_3} 4:{amp_col_4}")
                self._xlog.debug(f"📶 Amplitude: {amplitude.to_int(self.VU_METER_SCALE)} | VU Meter Columns: 1:0 2:{amp_col_2} 3:{amp_col_3} 4:{amp_col_4}")

                # Make it to speak
                self._output_stream.write(int_data)


            self._output_stream.stop()
            
        # Restore the speaker and microphone states
        self.write_shared_memory_flag(SHARED_SPEAKER_BUSY, False)
        # self.write_shared_memory_flag(SHARED_MICROPHONE_MUTED, previous_mic_state)
    
    def pause_mic(self):
        self.write_shared_memory_flag(SHARED_MICROPHONE_MUTED, True)

    def resume_mic(self):
        self.write_shared_memory_flag(SHARED_MICROPHONE_MUTED, False)