from multiprocessing import shared_memory
import time

from pyxavi import Config, Dictionary

from definitions import SHARED_MEMORY_FLAGS, SHARED_EINK_BUSY, SHARED_MATRIX_BUSY, SHARED_SPEAKER_BUSY, SHARED_LCD_BUSY, SHARED_MICROPHONE_MUTED,\
    SHARED_CHATBOT_BUSY, SHARED_CHATBOT_ANSWER_IS_ERROR, SHARED_EINK_IDLE_MODE, SHARED_LCD_IDLE_MODE,\
    SHARED_MEMORY_VU_METER, SHARED_VU_COL_1, SHARED_VU_COL_2, SHARED_VU_COL_3, SHARED_VU_COL_4,\
    QUEUE_SPEAKER, QUEUE_EINK, QUEUE_MATRIX
from pitxu.lib.abstract.pyxavi import PyXavi

class SharedMemoryManager(PyXavi):

    _shared_memory_flags: shared_memory.ShareableList = None
    _shared_memory_vu_meter: shared_memory.ShareableList = None
    _shared_flags: dict[str, int] = {
        "eink_busy": SHARED_EINK_BUSY,
        "matrix_busy": SHARED_MATRIX_BUSY,
        "speaker_busy": SHARED_SPEAKER_BUSY,
        "lcd_busy": SHARED_LCD_BUSY,
        # On purpose not including Microphone in the busy waiters, as it does not block other processes
        # "microphone_muted": SHARED_MICROPHONE_MUTED,
    }
    _shared_vu_meter_columns: dict[str, int] = {
        "col_1": SHARED_VU_COL_1,
        "col_2": SHARED_VU_COL_2,
        "col_3": SHARED_VU_COL_3,
        "col_4": SHARED_VU_COL_4,
    }
    _map_index_to_flag: dict[int, str] = {
        SHARED_EINK_BUSY: "eink_busy",
        SHARED_MATRIX_BUSY: "matrix_busy",
        SHARED_SPEAKER_BUSY: "speaker_busy",
        SHARED_LCD_BUSY: "lcd_busy",
        SHARED_MICROPHONE_MUTED: "microphone_muted",
        SHARED_CHATBOT_BUSY: "chatbot_busy",
        SHARED_CHATBOT_ANSWER_IS_ERROR: "chatbot_answer_is_error",
        SHARED_EINK_IDLE_MODE: "eink_idle_mode",
        SHARED_LCD_IDLE_MODE: "lcd_idle_mode",
    }

    WAITING_SLEEP_SECONDS = 0.01

    def __init__(self, config: Config = None, params: Dictionary = None, **kwargs):
        self.init_pyxavi(config=config, params=params, **kwargs)

        self._xlog.debug("Initializing SharedMemoryManager")

        super(SharedMemoryManager, self).__init__()
    
    def initialize_new_shared_memory_flags(self):
        # First of all, try to initialize new shared memory, in case it does not exist yet
        if self._shared_memory_flags is not None:
            self._xlog.debug("Shared Memory Flags already initialized")
            return
        self._initialize_new_shared_memory_flags()

        # Now, if the shared memory was not created, try to load existing one
        if self._shared_memory_flags is None:
            self._xlog.error("Shared Memory Flags is None, will try to clean previous state and retry")
            self._shared_memory_flags = shared_memory.SharedMemory(name=SHARED_MEMORY_FLAGS, create=False)
            self._xlog.debug("Cleaning previous Shared Memory Flags")
            self._shared_memory_flags.unlink()
            time.sleep(1)
            self._xlog.debug("Retrying to initialize new Shared Memory Flags")
            self._initialize_new_shared_memory_flags()
        
        # Final check
        if self._shared_memory_flags is None:
            self._xlog.error("Shared Memory Flags is None, cannot write flags, bubbling up the error")
            raise Exception("Shared Memory Flags is None, cannot write flags")

    def _initialize_new_shared_memory_flags(self):
        '''
        Initializes the shared memory for inter-process communication.
        '''
        try:
            self._xlog.debug("Initializing shared memory: " + SHARED_MEMORY_FLAGS)
            # Initialisating Shared Memory to handle execution flags between processes
            self._shared_memory_flags = shared_memory.ShareableList([
                False,  # speaker is busy (pause mic)
                False,  # e-ink is busy
                False,  # matrix is busy
                False,  # lcd is busy
                False,  # microphone is muted
                False,  # chatbot is busy
                False,  # chatbot answer is error
                False,  # eink idle mode (showing idle eyes)
                False   # lcd idle mode
            ], name=SHARED_MEMORY_FLAGS)
        except Exception as e:
            self._xlog.error("Failed to initialize shared memory: " + str(e))
    
    def initialize_new_shared_memory_vu_meter(self):
        # First of all, try to initialize new shared memory, in case it does not exist yet
        if self._shared_memory_vu_meter is not None:
            self._xlog.debug("Shared Memory VU Meter already initialized")
            return
        self._initialize_new_shared_memory_vu_meter()

        # Now, if the shared memory was not created, try to load existing one
        if self._shared_memory_vu_meter is None:
            self._xlog.error("Shared Memory VU Meter is None, will try to clean previous state and retry")
            self._shared_memory_vu_meter = shared_memory.SharedMemory(name=SHARED_MEMORY_VU_METER, create=False)
            self._xlog.debug("Cleaning previous Shared Memory VU Meter")
            self._shared_memory_vu_meter.unlink()
            time.sleep(1)
            self._xlog.debug("Retrying to initialize new Shared Memory VU Meter")
            self._initialize_new_shared_memory_vu_meter()
        
        # Final check
        if self._shared_memory_vu_meter is None:
            self._xlog.error("Shared Memory VU Meter is None, cannot write flags, bubbling up the error")
            raise Exception("Shared Memory VU Meter is None, cannot write flags")

    def _initialize_new_shared_memory_vu_meter(self):
        '''
        Initializes the shared memory for inter-process communication.
        '''
        try:
            self._xlog.debug("Initializing shared memory: " + SHARED_MEMORY_VU_METER)
            # Initialisating Shared Memory to handle execution flags between processes
            self._shared_memory_vu_meter = shared_memory.ShareableList([
                0,  # VU meter column 1
                0,  # VU meter column 2
                0,  # VU meter column 3
                0   # VU meter column 4
            ], name=SHARED_MEMORY_VU_METER)
            if self._shared_memory_vu_meter is None:
                self._xlog.error("Shared Memory VU Meter is None, cannot write VU meter values")
        except Exception as e:
            self._xlog.error("Failed to initialize shared memory: " + str(e))
    
    def initialize_existing_shared_memory_flags(self):
        self._xlog.info("Loading flags from Shared Memory")
        self._shared_memory_flags = shared_memory.ShareableList(name=SHARED_MEMORY_FLAGS)
        if self._shared_memory_flags is None:
            self._xlog.error("Shared Memory is None, cannot read flags")
    
    def initialize_existing_shared_memory_vu_meter(self):
        self._xlog.info("Loading VU meter from Shared Memory")
        self._shared_memory_vu_meter = shared_memory.ShareableList(name=SHARED_MEMORY_VU_METER)
        if self._shared_memory_vu_meter is None:
            self._xlog.error("Shared Memory is None, cannot read VU meter")

    def read_shared_memory_flag(self, index: int) -> bool:
        '''
        Reads a flag from shared memory at the given index
        '''
        if self._shared_memory_flags is None:
            self._xlog.error("Shared Memory is None, cannot read flag at index " + str(index))
            return None
        return self._shared_memory_flags[index]
    
    def write_shared_memory_flag(self, index: int, value: bool):
        '''
        Writes a flag to shared memory at the given index
        '''
        if self._shared_memory_flags is None:
            self._xlog.error("Shared Memory is None, cannot write flag at index " + str(index))
            return
        self._shared_memory_flags[index] = value
    
    def read_shared_memory_vu_meter_column(self, index: int) -> bool:
        '''
        Reads a flag from shared memory at the given index
        '''
        if self._shared_memory_vu_meter is None:
            self._xlog.error("Shared Memory is None, cannot read VU meter column at index " + str(index))
            return None
        return self._shared_memory_vu_meter[index]
    
    def write_shared_memory_vu_meter_column(self, index: int, value: bool):
        '''
        Writes a flag to shared memory at the given index
        '''
        if self._shared_memory_vu_meter is None:
            self._xlog.error("Shared Memory is None, cannot write VU meter column at index " + str(index))
            return
        self._shared_memory_vu_meter[index] = value
    
    def wait_for_all_busy_process_to_idle(self):
        # Now wait until the displays finish being busy
        self._xlog.debug("Waiting for all processes to get idle")
        busy_process = "Current processes busy flags: \n"
        for name, flag in self._shared_flags.items():
            busy_process += "- " + name + ": " + ("BUSY" if self.read_shared_memory_flag(flag) else "IDLE") + "\n"
        self._xlog.debug(busy_process)
        total_sleeping = 0
        while any(self.read_shared_memory_flag(flag) for flag in self._shared_flags.values()):
            total_sleeping += self.WAITING_SLEEP_SECONDS
            time.sleep(self.WAITING_SLEEP_SECONDS)
        self._xlog.debug("All processes are idle now. I've sleept " + str(total_sleeping) + "s.")
    
    def wait_for_busy_process_to_idle(self, memory_position: int):
        memory_position_name = self._map_index_to_flag.get(memory_position, "unknown")
        self._xlog.debug(f"Waiting for the process {memory_position_name} to idle. It's now: " + ("BUSY" if self.read_shared_memory_flag(memory_position) else "IDLE") + ".")
        total_sleeping = 0
        while self.read_shared_memory_flag(memory_position):
            total_sleeping += self.WAITING_SLEEP_SECONDS
            time.sleep(self.WAITING_SLEEP_SECONDS)
        self._xlog.debug(f"The process {memory_position_name} is idle now. I've sleept " + str(total_sleeping) + "s.")

    def close(self):
        if self._shared_memory_flags is not None:
            self._xlog.debug("Closing Shared Memory Flags")
            self._shared_memory_flags.shm.close()
            self._shared_memory_flags.shm.unlink()
        
        if self._shared_memory_vu_meter is not None:
            self._xlog.debug("Closing Shared Memory VU Meter")
            self._shared_memory_vu_meter.shm.close()
            self._shared_memory_vu_meter.shm.unlink()
    
    

