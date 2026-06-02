from multiprocessing import shared_memory
import time

from pyxavi import Config, Dictionary, full_stack

from definitions import SHARED_MEMORY_FLAGS, SHARED_EINK_BUSY, SHARED_MATRIX_BUSY, \
    SHARED_SPEAKER_BUSY, SHARED_LCD_BUSY, SHARED_DSI_LCD_BUSY, SHARED_MICROPHONE_MUTED,\
    SHARED_CHATBOT_BUSY, SHARED_CHATBOT_ANSWER_IS_ERROR, SHARED_IDLE_MODE, SHARED_LCD_IDLE_MODE, \
    SHARED_DSI_LCD_IDLE_MODE, SHARED_NETWORK_BUSY, SHARED_VAD_DETECTED, SHARED_SUPPORT_BUSY, SHARED_STT_BUSY, \
    SHARED_TRANSCRIBER_BUSY, \
    SHARED_MEMORY_VALUES, SHARED_DYNAMIC_RMS_SILENCE_THRESHOLD
from pitxu.lib.abstract.pyxavi import PyXavi

class SharedMemoryManager(PyXavi):

    _shared_memory_flags: shared_memory.ShareableList = None
    _shared_memory_values: shared_memory.ShareableList = None

    _shared_flags: dict[str, int] = {
        "eink_busy": SHARED_EINK_BUSY,
        "matrix_busy": SHARED_MATRIX_BUSY,
        "speaker_busy": SHARED_SPEAKER_BUSY,
        "lcd_busy": SHARED_LCD_BUSY,
        "dsi_lcd_busy": SHARED_DSI_LCD_BUSY,
        # On purpose not including Microphone in the busy waiters, as it does not block other processes
        # "microphone_muted": SHARED_MICROPHONE_MUTED,
        "chatbot_busy": SHARED_CHATBOT_BUSY,
        "network_busy": SHARED_NETWORK_BUSY,
        "vad_detected": SHARED_VAD_DETECTED,
        "support_busy": SHARED_SUPPORT_BUSY,
        "stt_busy": SHARED_STT_BUSY,
        "transcriber_busy": SHARED_TRANSCRIBER_BUSY
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
        SHARED_IDLE_MODE: "eink_idle_mode",
        SHARED_LCD_IDLE_MODE: "lcd_idle_mode",
        SHARED_DSI_LCD_IDLE_MODE: "dsi_lcd_idle_mode",
        SHARED_NETWORK_BUSY: "network_busy",
        SHARED_VAD_DETECTED: "vad_detected",
        SHARED_SUPPORT_BUSY: "support_busy",
        SHARED_STT_BUSY: "stt_busy",
        SHARED_TRANSCRIBER_BUSY: "transcriber_busy"
    }
    _shared_values: dict[str, int] = {
        "dynamic_rms_silence_threshold": SHARED_DYNAMIC_RMS_SILENCE_THRESHOLD
    }
    # TODO: consider generating this map automatically together with xprocess_pool, painter_busy_flags, etc.
    _map_index_to_value: dict[int, str] = {
        SHARED_DYNAMIC_RMS_SILENCE_THRESHOLD: "dynamic_rms_silence_threshold"
    }

    WAITING_SLEEP_SECONDS: float = 0.01
    WAITING_FOR_QUEUES_TIMEOUT_SECONDS: int = 5

    def __init__(self, config: Config = None, params: Dictionary = None, **kwargs):
        self.init_pyxavi(config=config, params=params, **kwargs)

        self._xlog.debug("Initializing SharedMemoryManager")

        super(SharedMemoryManager, self).__init__()
    
    # --- START INIT SHARED MEM FLAGS ---
    
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
                False,  # communication busy
                False,  # user is speaking
                False,  # support is busy
                False,  # stt is busy
                False,  # transcriber is busy
            ], name=SHARED_MEMORY_FLAGS)
        except Exception as e:
            self._xlog.error("Failed to initialize shared memory: " + str(e))
    
    def initialize_existing_shared_memory_flags(self):
        self._xlog.info("Loading flags from Shared Memory")
        self._shared_memory_flags = shared_memory.ShareableList(name=SHARED_MEMORY_FLAGS)
        if self._shared_memory_flags is None:
            self._xlog.error("Shared Memory is None, cannot read flags")
    
    # --- END INIT SHARED MEM FLAGS ---

    # --- START INIT SHARED MEM VALUES ---
    
    def initialize_new_shared_memory_values(self):
        # First of all, try to initialize new shared memory, in case it does not exist yet
        if self._shared_memory_values is not None:
            self._xlog.debug("Shared Memory Values already initialized")
            return
        self._initialize_new_shared_memory_values()

        # Now, if the shared memory was not created, try to load existing one
        if self._shared_memory_values is None:
            self._xlog.error("Shared Memory Values is None, will try to clean previous state and retry")
            self._shared_memory_values = shared_memory.SharedMemory(name=SHARED_MEMORY_VALUES, create=False)
            self._xlog.debug("Cleaning previous Shared Memory Values")
            self._shared_memory_values.unlink()
            time.sleep(1)
            self._xlog.debug("Retrying to initialize new Shared Memory Values")
            self._initialize_new_shared_memory_values()
        
        # Final check
        if self._shared_memory_values is None:
            self._xlog.error("Shared Memory Values is None, cannot write values, bubbling up the error")
            raise Exception("Shared Memory Values is None, cannot write values")

    def _initialize_new_shared_memory_values(self):
        '''
        Initializes the shared memory for inter-process communication.
        '''
        try:
            self._xlog.debug("Initializing shared memory: " + SHARED_MEMORY_VALUES)
            # Initialisating Shared Memory to handle execution flags between processes
            # TODO: consider using a more compact representation (bitmask) if performance/memory becomes an issue
            self._shared_memory_values = shared_memory.ShareableList([
                0.0,    # dynamic RMS silence threshold
            ], name=SHARED_MEMORY_VALUES)
        except Exception as e:
            self._xlog.error("Failed to initialize shared memory: " + str(e))
    
    def initialize_existing_shared_memory_values(self):
        self._xlog.info("Loading values from Shared Memory")
        self._shared_memory_values = shared_memory.ShareableList(name=SHARED_MEMORY_VALUES)
        if self._shared_memory_values is None:
            self._xlog.error("Shared Memory is None, cannot read values")
    
    # --- END INIT SHARED MEM VALUES ---

    def read_shared_memory_flag(self, index: int) -> bool | None:
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
    
    def read_shared_memory_value(self, index: int) -> float | None:
        '''
        Reads a value from shared memory at the given index
        '''
        if self._shared_memory_values is None:
            self._xlog.error("Shared Memory is None, cannot read value at index " + str(index))
            return None
        return float(self._shared_memory_values[index])
    
    def write_shared_memory_value(self, index: int, value: float):
        '''
        Writes a value to shared memory at the given index
        '''
        if self._shared_memory_values is None:
            self._xlog.error("Shared Memory is None, cannot write value at index " + str(index))
            return
        self._shared_memory_values[index] = value
    
    def wait_for_all_busy_process_to_idle(self):
        # Now wait until the displays finish being busy
        self._xlog.debug("Waiting for all processes to get idle")
        self.log_summary(
            "Current processes busy flags", 
            [(name, "BUSY" if self.read_shared_memory_flag(flag) else "IDLE") for name, flag in self._shared_flags.items()])
        total_sleeping = 0
        start_time = time.time()
        forced_break = False
        while any(self.read_shared_memory_flag(flag) for flag in self._shared_flags.values()):
            if time.time() - start_time > self.WAITING_FOR_QUEUES_TIMEOUT_SECONDS:
                self._xlog.error("Timeout reached while waiting for all processes to idle.")
                forced_break = True
                break
            total_sleeping += self.WAITING_SLEEP_SECONDS
            time.sleep(self.WAITING_SLEEP_SECONDS)
        if not forced_break:
            self._xlog.debug("All processes are idle now. I've slept " + str(round(total_sleeping, 2)) + "s.")
        else:
            self._xlog.debug("Forced break after sleeping for " + str(round(total_sleeping, 2)) + "s while waiting for all processes to idle.")
    
    def wait_for_busy_process_to_idle(self, memory_position: int):
        memory_position_name = self._map_index_to_flag.get(memory_position, "unknown")
        self._xlog.debug(f"Waiting for the process {memory_position_name} to idle. It's now: " + ("BUSY" if self.read_shared_memory_flag(memory_position) else "IDLE") + ".")
        total_sleeping = 0
        start_time = time.time()
        forced_break = False
        while self.read_shared_memory_flag(memory_position):
            if time.time() - start_time > self.WAITING_FOR_QUEUES_TIMEOUT_SECONDS:
                self._xlog.error(f"Timeout reached while waiting for process {memory_position_name} to idle.")
                forced_break = True
                break
            total_sleeping += self.WAITING_SLEEP_SECONDS
            time.sleep(self.WAITING_SLEEP_SECONDS)
        if not forced_break:
            self._xlog.debug(f"The process {memory_position_name} is idle now. I've slept " + str(round(total_sleeping, 2)) + "s.")
        else:
            self._xlog.debug(f"Forced break after sleeping for " + str(round(total_sleeping, 2)) + f"s while waiting for process {memory_position_name} to idle.")
    
    def wait_for_busy_process_to_be_busy(self, memory_position: int):
        memory_position_name = self._map_index_to_flag.get(memory_position, "unknown")
        self._xlog.debug(f"Waiting for the process {memory_position_name} to be busy. It's now: " + ("BUSY" if self.read_shared_memory_flag(memory_position) else "IDLE") + ".")
        total_sleeping = 0
        while not self.read_shared_memory_flag(memory_position):
            total_sleeping += self.WAITING_SLEEP_SECONDS
            time.sleep(self.WAITING_SLEEP_SECONDS)
        self._xlog.debug(f"The process {memory_position_name} is busy now. I've slept " + str(round(total_sleeping, 2)) + "s.")
    
    def force_all_flags_to_idle(self, is_closing=False):
        self._xlog.debug("Forcing all flags to idle.")
        for name, flag in self._shared_flags.items():
            try:
                if self.read_shared_memory_flag(flag):
                    self._xlog.debug(f"Flag {name} was busy, setting it to idle")
                    self.write_shared_memory_flag(flag, False)
            except TypeError as e:
                if not is_closing:
                    # Can be that at the moment of closing, the shared memory is also getting closed in parallel.
                    # That's actually not nice, but I need to iterate the closing order, so by now
                    # We just fail silently and move on to the next one.
                    self._xlog.error(f"🛑 Failed to read/write flag {name} at index {flag}: " + str(e))
                    self._xlog.debug(full_stack())

    def close(self):
        """
        Close the Shared Memory spaces by unlinking the shared memory objects.
        This should be called when the application is closing to clean up resources.
        Please call this ONLY FROM the XProcessPool.close() (so, by the Interaction.close()),
        otherwise the memory is tried to be closed several times.
        """
        if self._shared_memory_flags is not None:
            self._xlog.debug("Closing Shared Memory Flags")
            try:
                self._shared_memory_flags.shm.close()
                self._shared_memory_flags.shm.unlink()
            except FileNotFoundError as e:
                self._xlog.info("Shared Memory Flags already unlinked: " + str(e))
        if self._shared_memory_values is not None:
            self._xlog.debug("Closing Shared Memory Values")
            try:
                self._shared_memory_values.shm.close()
                self._shared_memory_values.shm.unlink()
            except FileNotFoundError as e:
                self._xlog.info("Shared Memory Values already unlinked: " + str(e))
    

