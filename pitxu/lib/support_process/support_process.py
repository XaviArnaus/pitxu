import logging

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction

from pitxu.lib.support_process.dumper import Dumper
from pitxu.lib.support_process.summarizer import Summarizer
from pitxu.lib.utils.memory_consolidator import MemoryConsolidator

import numpy as np

class SupportProcess(Xprocess):
    """
    Class to execute some support actions outside the common processes, to avoid blocking basically the Main thread
    and the audio capturing.
    The idea is to use this process with tasks done via multiprocess, to allow having multiple support tasks running at the same time if needed.
    """

    dumper: Dumper = None
    summarizer: Summarizer = None
    consolidator: MemoryConsolidator = None

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

        self.summarizer = Summarizer(config=self._xconfig, params=self._xparams)

        self.consolidator = MemoryConsolidator(
            config=self._xconfig, params=self._xparams, should_abort=self._something_is_waiting)

    def finish(self):
        self._xlog.debug("Closing Memory Consolidator in Support Worker")
        if self.consolidator is not None:
            self.consolidator.close()
        self._xlog.debug("Closing Summarizer in Support Worker")
        if self.summarizer is not None:
            self.summarizer.close()
        self._xlog.debug("Closing Dumper in Support Worker")
        if self.dumper is not None:
            self.dumper.close()
        self._xlog.debug("Done finishing Support Worker")
    
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
        
        if action == XprocAction.SUMMARIZE_CHATBOT_HISTORY_AND_STORE_IN_MEMORY:
            if isinstance(param, list):
                self.summarize_and_store_in_memory(param)
            elif isinstance(param, dict) and isinstance(param.get("history"), list):
                self.summarize_and_store_in_memory(param["history"], param.get("pending_id"))

        if action == XprocAction.CONSOLIDATE_MEMORY:
            self.consolidate_memory(param if isinstance(param, str) else "requested")
    
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
    
    def summarize_and_store_in_memory(self, chatbot_history: list[dict], pending_id: int = None) -> None:
        self._log_debug("Summarizing chatbot history and storing it in memory in Support Worker")
        self.summarizer.summarize_and_store_in_memory(chatbot_history, pending_id)

    def consolidate_memory(self, reason: str) -> None:
        self._xlog.info(f"Consolidating the memory in Support Worker [{reason}]")
        self.consolidator.run(reason=reason)

    def _something_is_waiting(self) -> bool:
        """
        Is there anything in the queue of this worker? The consolidation is long: when something arrives
        (the summary at closing, the FINISH) it gives way instead of making it wait.
        """
        try:
            return self._queue.qsize() > 0
        except (NotImplementedError, Exception):
            return False

    
