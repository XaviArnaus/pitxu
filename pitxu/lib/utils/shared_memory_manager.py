from multiprocessing import shared_memory
import time

from pyxavi import Config, Dictionary

from definitions import SHARED_MEMORY_FLAGS, SHARED_EINK_BUSY, SHARED_MATRIX_BUSY, SHARED_SPEAKER_BUSY, SHARED_MICROPHONE_MUTED,\
    SHARED_MEMORY_VU_METER, SHARED_VU_COL_1, SHARED_VU_COL_2, SHARED_VU_COL_3, SHARED_VU_COL_4,\
    SHARED_GPIO_BUTTONS, SHARED_GPIO_LEDS
from pitxu.lib.abstract.pyxavi import PyXavi

class SharedMemoryManager(PyXavi):

    _shared_memory_flags: shared_memory.ShareableList = None
    _shared_memory_vu_meter: shared_memory.ShareableList = None
    _shared_memory_gpio_switch: shared_memory.ShareableList = None
    _shared_memory_gpio_led: shared_memory.ShareableList = None

    _shared_flags: dict[str, int] = {
        "eink_busy": SHARED_EINK_BUSY,
        "matrix_busy": SHARED_MATRIX_BUSY,
        "speaker_busy": SHARED_SPEAKER_BUSY,
        # On purpose not including Microphone in the busy waiters, as it does not block other processes
        # "microphone_muted": SHARED_MICROPHONE_MUTED,
    }
    _shared_vu_meter_columns: dict[str, int] = {
        "col_1": SHARED_VU_COL_1,
        "col_2": SHARED_VU_COL_2,
        "col_3": SHARED_VU_COL_3,
        "col_4": SHARED_VU_COL_4,
    }

    def __init__(self, config: Config = None, params: Dictionary = None, **kwargs):
        self.init_pyxavi(config=config, params=params, **kwargs)

        self._xlog.debug("Initializing SharedMemoryManager")

        super(SharedMemoryManager, self).__init__()

    def initialize_new_shared_memory_flags(self):
        '''
        Initializes the shared memory for inter-process communication.
        '''
        try:
            self._xlog.debug("Initializing Shared Memory Flags: " + SHARED_MEMORY_FLAGS)
            # Initialisating Shared Memory to handle execution flags between processes
            self._shared_memory_flags = shared_memory.ShareableList([
                False,  # speaker is busy (pause mic)
                False,  # e-ink is busy
                False,  # matrix is busy
                False,  # microphone is muted
                False,  # chatbot is busy
            ], name=SHARED_MEMORY_FLAGS)
            if self._shared_memory_flags is None:
                self._xlog.error("Shared Memory Flags is None, cannot write flags")
        except Exception as e:
            self._xlog.error("Failed to initialize Shared Memory Flags: " + str(e))
    
    def initialize_new_shared_memory_vu_meter(self):
        '''
        Initializes the shared memory for inter-process communication.
        '''
        try:
            self._xlog.debug("Initializing Shared Memory VU Meter: " + SHARED_MEMORY_VU_METER)
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
            self._xlog.error("Failed to initialize Shared Memory VU Meter: " + str(e))

    def initialize_new_shared_memory_gpio_buttons(self):
        '''
        Initializes the shared memory for inter-process communication.
        '''
        try:
            self._xlog.debug("Initializing Shared Memory GPIO Buttons: " + SHARED_GPIO_BUTTONS)
            # Initialisating Shared Memory to handle execution flags between processes
            self._shared_memory_gpio_switch = shared_memory.ShareableList([
                False,  # button green is pressed
            ], name=SHARED_GPIO_BUTTONS)
            if self._shared_memory_gpio_switch is None:
                self._xlog.error("Shared Memory GPIO Buttons is None, cannot write button states")
        except Exception as e:
            self._xlog.error("Failed to initialize Shared Memory GPIO Buttons: " + str(e))
    
    def initialize_new_shared_memory_gpio_leds(self):
        '''
        Initializes the shared memory for inter-process communication.
        '''
        try:
            self._xlog.debug("Initializing Shared Memory GPIO LEDs: " + SHARED_GPIO_LEDS)
            # Initialisating Shared Memory to handle execution flags between processes
            self._shared_memory_gpio_led = shared_memory.ShareableList([
                False,  # LED blue is on
            ], name=SHARED_GPIO_LEDS)
            if self._shared_memory_gpio_led is None:
                self._xlog.error("Shared Memory GPIO LEDs is None, cannot write LED states")
        except Exception as e:
            self._xlog.error("Failed to initialize Shared Memory GPIO LEDs: " + str(e))

    def initialize_existing_shared_memory_gpio_leds(self):
        self._xlog.info("Loading GPIO LEDs from Shared Memory")
        self._shared_memory_gpio_led = shared_memory.ShareableList(name=SHARED_GPIO_LEDS)
        if self._shared_memory_gpio_led is None:
            self._xlog.error("Shared Memory is None, cannot read GPIO LEDs")

    def initialize_existing_shared_memory_gpio_buttons(self):
        self._xlog.info("Loading GPIO buttons from Shared Memory")
        self._shared_memory_gpio_switch = shared_memory.ShareableList(name=SHARED_GPIO_BUTTONS)
        if self._shared_memory_gpio_switch is None:
            self._xlog.error("Shared Memory is None, cannot read GPIO buttons")

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
    
    def read_shared_memory_gpio_button(self, index: int) -> bool:
        '''
        Reads a flag from shared memory at the given index
        '''
        if self._shared_memory_gpio_switch is None:
            self._xlog.error("Shared Memory is None, cannot read GPIO button at index " + str(index))
            return None
        return self._shared_memory_gpio_switch[index]

    def write_shared_memory_gpio_button(self, index: int, value: bool):
        '''
        Writes a flag to shared memory at the given index
        '''
        if self._shared_memory_gpio_switch is None:
            self._xlog.error("Shared Memory is None, cannot write GPIO button at index " + str(index))
            return
        self._shared_memory_gpio_switch[index] = value
    
    def read_shared_memory_gpio_led(self, index: int) -> bool:
        '''
        Reads a flag from shared memory at the given index
        '''
        if self._shared_memory_gpio_led is None:
            self._xlog.error("Shared Memory is None, cannot read GPIO LED at index " + str(index))
            return None
        return self._shared_memory_gpio_led[index]

    def write_shared_memory_gpio_led(self, index: int, value: bool):
        '''
        Writes a flag to shared memory at the given index
        '''
        if self._shared_memory_gpio_led is None:
            self._xlog.error("Shared Memory is None, cannot write GPIO LED at index " + str(index))
            return
        self._shared_memory_gpio_led[index] = value
    
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
        if self._shared_memory_flags is not None:
            self._xlog.debug("Closing Shared Memory Flags")
            self._shared_memory_flags.shm.close()
            self._shared_memory_flags.shm.unlink()
        
        if self._shared_memory_vu_meter is not None:
            self._xlog.debug("Closing Shared Memory VU Meter")
            self._shared_memory_vu_meter.shm.close()
            self._shared_memory_vu_meter.shm.unlink()
    
    

