from multiprocessing import shared_memory
import time

from pyxavi import Config, Dictionary

from definitions import SHARED_MEMORY_FLAGS, SHARED_EINK_BUSY, SHARED_MATRIX_BUSY, SHARED_SPEAKER_BUSY, SHARED_LCD_BUSY, SHARED_DSI_LCD_BUSY, SHARED_MICROPHONE_MUTED,\
    SHARED_CHATBOT_BUSY, SHARED_CHATBOT_ANSWER_IS_ERROR, SHARED_EINK_IDLE_MODE, SHARED_LCD_IDLE_MODE, SHARED_DSI_LCD_IDLE_MODE, SHARED_NETWORK_BUSY
from pitxu.lib.abstract.pyxavi import PyXavi

class SharedMemoryManager(PyXavi):

    _shared_memory_flags: shared_memory.ShareableList = None
    _shared_flags: dict[str, int] = {
        "eink_busy": SHARED_EINK_BUSY,
        "matrix_busy": SHARED_MATRIX_BUSY,
        "speaker_busy": SHARED_SPEAKER_BUSY,
        "lcd_busy": SHARED_LCD_BUSY,
        "dsi_lcd_busy": SHARED_DSI_LCD_BUSY,
        # On purpose not including Microphone in the busy waiters, as it does not block other processes
        # "microphone_muted": SHARED_MICROPHONE_MUTED,
        "chatbot_busy": SHARED_CHATBOT_BUSY,
        "communication_busy": SHARED_NETWORK_BUSY
    }
    # TODO: consider generating this map automatically together with xprocess_pool, painter_busy_flags, etc.
    _map_index_to_flag: dict[int, str] = {
        SHARED_EINK_BUSY: "eink_busy",
        SHARED_MATRIX_BUSY: "matrix_busy",
        SHARED_SPEAKER_BUSY: "speaker_busy",
        SHARED_LCD_BUSY: "lcd_busy",
        SHARED_DSI_LCD_BUSY: "dsi_lcd_busy",
        SHARED_MICROPHONE_MUTED: "microphone_muted",
        SHARED_CHATBOT_BUSY: "chatbot_busy",
        SHARED_CHATBOT_ANSWER_IS_ERROR: "chatbot_answer_is_error",
        SHARED_EINK_IDLE_MODE: "eink_idle_mode",
        SHARED_LCD_IDLE_MODE: "lcd_idle_mode",
        SHARED_DSI_LCD_IDLE_MODE: "dsi_lcd_idle_mode",
        SHARED_NETWORK_BUSY: "communication_busy"
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
            # TODO: consider using a more compact representation (bitmask) if performance/memory becomes an issue
            self._shared_memory_flags = shared_memory.ShareableList([
                False,  # speaker is busy (pause mic)
                False,  # e-ink is busy
                False,  # matrix is busy
                False,  # lcd is busy
                False,  # dsi lcd is busy
                False,  # microphone is muted
                False,  # chatbot is busy
                False,  # chatbot answer is error
                False,  # eink idle mode (showing idle eyes)
                False,  # lcd idle mode
                False,  # dsi lcd idle mode
                False   # communication busy
            ], name=SHARED_MEMORY_FLAGS)
        except Exception as e:
            self._xlog.error("Failed to initialize shared memory: " + str(e))
    
    def initialize_existing_shared_memory_flags(self):
        self._xlog.info("Loading flags from Shared Memory")
        self._shared_memory_flags = shared_memory.ShareableList(name=SHARED_MEMORY_FLAGS)
        if self._shared_memory_flags is None:
            self._xlog.error("Shared Memory is None, cannot read flags")

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
        self._xlog.debug("All processes are idle now. I've slept " + str(round(total_sleeping, 2)) + "s.")
    
    def wait_for_busy_process_to_idle(self, memory_position: int):
        memory_position_name = self._map_index_to_flag.get(memory_position, "unknown")
        self._xlog.debug(f"Waiting for the process {memory_position_name} to idle. It's now: " + ("BUSY" if self.read_shared_memory_flag(memory_position) else "IDLE") + ".")
        total_sleeping = 0
        while self.read_shared_memory_flag(memory_position):
            total_sleeping += self.WAITING_SLEEP_SECONDS
            time.sleep(self.WAITING_SLEEP_SECONDS)
        self._xlog.debug(f"The process {memory_position_name} is idle now. I've slept " + str(round(total_sleeping, 2)) + "s.")
    
    def wait_for_busy_process_to_be_busy(self, memory_position: int):
        memory_position_name = self._map_index_to_flag.get(memory_position, "unknown")
        self._xlog.debug(f"Waiting for the process {memory_position_name} to be busy. It's now: " + ("BUSY" if self.read_shared_memory_flag(memory_position) else "IDLE") + ".")
        total_sleeping = 0
        while not self.read_shared_memory_flag(memory_position):
            total_sleeping += self.WAITING_SLEEP_SECONDS
            time.sleep(self.WAITING_SLEEP_SECONDS)
        self._xlog.debug(f"The process {memory_position_name} is busy now. I've slept " + str(round(total_sleeping, 2)) + "s.")

    def close(self):
        if self._shared_memory_flags is not None:
            self._xlog.debug("Closing Shared Memory Flags")
            self._shared_memory_flags.shm.close()
            self._shared_memory_flags.shm.unlink()
    
    

