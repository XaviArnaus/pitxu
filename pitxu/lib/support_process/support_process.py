import logging, time
from piper.voice import PiperVoice

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction

from pitxu.lib.support_process.dumper import Dumper

from definitions import ROOT_DIR, SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY

import numpy as np

class SupportProcess(Xprocess):
    """
    Class to execute some support actions outside the common processes, to avoid blocking basically the Main thread
    and the audio capturing.
    The idea is to use this process with tasks done via threading, to allow having multiple support tasks running at the same time if needed.
    """

    dumper: Dumper = None
    

    def get_process_name(self) -> str:
        return "Support"

    def initialize(self):
        self._xlog.info("Initializing Support Worker")

        logging.getLogger("matplotlib.font_manager").setLevel(self._xconfig.get("libs_logger.matplotlib.loglevel", logging.WARNING))

        # Dumper requires the following parameters in xparams:
        # - samplerate (int): The sample rate to use for the audio files. Default is 16000.
        # - lowcut_freq (int): The low cut frequency for the bandpass filter. Default is 300.
        # - highcut_freq (int): The high cut frequency for the bandpass filter. Default is 3400.
        self.dumper = Dumper(config=self._xconfig, params=self._xparams)

    def finish(self):
        # self._xlog.debug("Closing Dumper in Support Worker")
        # self._xlog.debug("Done finishing Support Worker")
        pass
    
    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        
        if action == XprocAction.ACCUMULATE_AUDIO:
            self.accumulate_audio(param, preprocessed=False)
        
        if action == XprocAction.ACCUMULATE_PREPROCESSED_AUDIO:
            self.accumulate_audio(param, preprocessed=True)
        
        if action == XprocAction.CLEAR_AUDIOS:
            self.clear_accumulated_audio()
        
        if action == XprocAction.DUMP_AUDIO:
            self.dump_accumulated_audio(preprocessed=False)
        
        if action == XprocAction.DUMP_PREPROCESSED_AUDIO:
            self.dump_accumulated_audio(preprocessed=True)
        
        if action == XprocAction.PLOT_AUDIO:
            self.plot_accumulated_audio()
        
        if action == XprocAction.DUMP_ALL:
            # With the context manager, the timestamp for all dumps will be unified,
            # so they can be easily correlated in the filesystem layer.
            with self.dumper.unified_timestamp():
                self.dump_accumulated_audio(preprocessed=False)
                self.dump_accumulated_audio(preprocessed=True)
                self.plot_accumulated_audio()
    
    def accumulate_audio(self, audio_data_np: np.ndarray, preprocessed: bool = False):
        self._log_debug(f"Accummulating {'preprocessed' if preprocessed else 'raw'} audio data in Support Worker")
        self.dumper.accumulate_audio(audio_data_np, preprocessed)
    
    def clear_accumulated_audio(self):
        self._log_debug("Clearing accumulated audio data in Support Worker")
        self.dumper.clear_accumulated_audios()
    
    def dump_accumulated_audio(self, preprocessed: bool = False):
        self._log_debug(f"Dumping {'preprocessed' if preprocessed else 'raw'} accumulated audio data in Support Worker")
        self.dumper.dump_accumulated_audio(preprocessed)
    
    def plot_accumulated_audio(self):
        self._log_debug(f"Plotting accumulated audio data in Support Worker")
        self.dumper.plot_accumulated_audio()

    
