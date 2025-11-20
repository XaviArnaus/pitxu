from multiprocessing import shared_memory
import time

from pyxavi import Config, Dictionary

from definitions import SHARED_MEMORY_FLAGS, SHARED_EINK_BUSY, SHARED_MATRIX_BUSY, SHARED_SPEAKER_BUSY, SHARED_MICROPHONE_MUTED
from pitxu.lib.abstract.pyxavi import PyXavi

class SharedMemoryManager(PyXavi):

    _shared_memory: shared_memory.ShareableList = None
    _shared_flags: dict[str, int] = {
        "eink_busy": SHARED_EINK_BUSY,
        "matrix_busy": SHARED_MATRIX_BUSY,
        "speaker_busy": SHARED_SPEAKER_BUSY,
        # On purpose not including Microphone in the busy waiters, as it does not block other processes
        # "microphone_muted": SHARED_MICROPHONE_MUTED,
    }

    def __init__(self, config: Config = None, params: Dictionary = None, **kwargs):
        self.init_pyxavi(config=config, params=params, **kwargs)

        self._xlog.debug("Initializing SharedMemoryManager")

        super(SharedMemoryManager, self).__init__()

    def initialize_new_shared_memory(self):
        '''
        Initializes the shared memory for inter-process communication.
        '''
        try:
            self._xlog.debug("Initializing shared memory: " + SHARED_MEMORY_FLAGS)
            # Initialisating Shared Memory to handle execution flags between processes
            self._shared_memory = shared_memory.ShareableList([
                False,  # speaker is busy (pause mic)
                False,  # e-ink is busy
                False,  # matrix is busy
                False   # microphone is muted
            ], name=SHARED_MEMORY_FLAGS)
            if self._shared_memory is None:
                self._xlog.error("Shared Memory is None, cannot write flags")
        except Exception as e:
            self._xlog.error("Failed to initialize shared memory: " + str(e))
    
    def initialize_existing_shared_memory(self):
        self._xlog.info("Loading flags from Shared Memory")
        self._shared_memory = shared_memory.ShareableList(name=SHARED_MEMORY_FLAGS)
        if self._shared_memory is None:
            self._xlog.error("Shared Memory is None, cannot read flags")

    def read_shared_memory_flag(self, index: int) -> bool:
        '''
        Reads a flag from shared memory at the given index
        '''
        if self._shared_memory is None:
            self._xlog.error("Shared Memory is None, cannot read flag at index " + str(index))
            return None
        return self._shared_memory[index]
    
    def write_shared_memory_flag(self, index: int, value: bool):
        '''
        Writes a flag to shared memory at the given index
        '''
        if self._shared_memory is None:
            self._xlog.error("Shared Memory is None, cannot write flag at index " + str(index))
            return
        self._shared_memory[index] = value
    
    def wait_for_all_busy_process_to_idle(self):
        # Now wait until the displays finish being busy
        self._xlog.debug("Waiting for all processes to get idle")
        busy_process = "Current processes busy flags: \n"
        for name, flag in self._shared_flags.items():
            busy_process += "- " + name + ": " + ("BUSY" if self.read_shared_memory_flag(flag) else "IDLE") + "\n"
        self._xlog.debug(busy_process)
        sleep_seconds = 0.5
        total_sleeping = 0
        while any(self.read_shared_memory_flag(flag) for flag in self._shared_flags.values()):
            total_sleeping += sleep_seconds
            time.sleep(sleep_seconds)
        self._xlog.debug("All processes are idle now. I've sleept " + str(total_sleeping) + "s.")
    
    def wait_for_busy_process_to_idle(self, memory_position: int):
        self._xlog.debug("Waiting for a process to idle. It's now: " + ("BUSY" if self.read_shared_memory_flag(memory_position) else "IDLE") + ".")
        sleep_seconds = 0.5
        total_sleeping = 0
        while self.read_shared_memory_flag(memory_position):
            total_sleeping += sleep_seconds
            time.sleep(sleep_seconds)
        self._xlog.debug("The process is idle now. I've sleept " + str(total_sleeping) + "s.")
    
    def close(self):
        if self._shared_memory is not None:
            self._xlog.debug("Closing Shared Memory")
            self._shared_memory.shm.close()
            self._shared_memory.shm.unlink()
    
    

