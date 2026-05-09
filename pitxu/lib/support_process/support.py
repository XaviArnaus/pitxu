from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.utils.xprocess_pool import XprocessPool
from pitxu.lib.support_process.support_process import SupportProcess
from pitxu.lib.objects import XprocAction

from definitions import QUEUE_SUPPORT, SHARED_SUPPORT_BUSY

from multiprocessing import JoinableQueue
import numpy as np

class Support(PyXavi):

    process_pool: XprocessPool = None

    input_queue: JoinableQueue = None
    output_queue: JoinableQueue = None
    output_queue_sentinel: object = None

    def __init__(self, config: Config, params: Dictionary):
        super(Support, self).init_pyxavi(config=config, params=params)
    
    def initialize(self):
        self._xlog.info("Initializing Support class")

        # Get the process pool from params, fail otherwise.
        if self._xparams.key_exists("process_pool"):
            self.process_pool = self._xparams.get("process_pool")
        else:
            raise ValueError("No XprocessPool provided in params to Support class")
        
        # Initialize the Support process in the pool, with the appropriate queues.
        initialized = self.process_pool.new_and_start(QUEUE_SUPPORT, SupportProcess, params=Dictionary({
            "initialize_from_main": False,
            "use_output_queue": True
        }))
        if not initialized:
            raise RuntimeError("Failed to initialize SupportProcess in the XprocessPool")
        
        self.input_queue = self.process_pool.get_queue(QUEUE_SUPPORT)
        self.output_queue = initialized.get("output_queue")
        self.output_queue_sentinel = initialized.get("sentinel_output_queue")
    
    def close(self):
        self._xlog.info("Closing Support class")

        # Close the Support process in the pool.
        self.process_pool.force_queue_to_empty(self.input_queue)

        self._xlog.info("Support class closed")
    
    def get_output_queue(self) -> JoinableQueue:
        return self.output_queue
    
    def get_output_queue_sentinel(self) -> object:
        return self.output_queue_sentinel
    
    # ---- Support actions ----

    def accumulate_audio(self, audio_data_np: np.ndarray, preprocessed: bool = False):
        self.process_pool.send(QUEUE_SUPPORT, 
                               XprocAction.ACCUMULATE_PREPROCESSED_AUDIO if preprocessed else XprocAction.ACCUMULATE_AUDIO, 
                               audio_data_np)
    
    def clear_accumulated_audio(self):
        self.process_pool.send(QUEUE_SUPPORT, XprocAction.CLEAR_AUDIOS, None)
    
    def dump_accumulated_audio(self, preprocessed: bool = False):
        self.process_pool.send(QUEUE_SUPPORT, 
                               XprocAction.DUMP_PREPROCESSED_AUDIO if preprocessed else XprocAction.DUMP_AUDIO)
    
    def plot_accumulated_audio(self):
        self.process_pool.send(QUEUE_SUPPORT, XprocAction.PLOT_AUDIO)
    
    def dump_and_plot_all(self):
        """
        Dumps all accumulated audio (raw and preprocessed) and plots them.
        Sends 1 action to the process queue, and there it uses the context manager to fit the same timestamp for all.
        """
        self.process_pool.send(QUEUE_SUPPORT, XprocAction.DUMP_ALL)
    
    def summarize_and_store_in_memory(self, chatbot_history: list[dict]) -> None:
        self.process_pool.send(QUEUE_SUPPORT, 
                               XprocAction.SUMMARIZE_CHATBOT_HISTORY_AND_STORE_IN_MEMORY, 
                               chatbot_history)