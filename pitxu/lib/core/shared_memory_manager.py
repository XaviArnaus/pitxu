from multiprocessing import shared_memory
import time

from pyxavi import Config, Dictionary, full_stack

from definitions import SHARED_MEMORY_FLAGS, SHARED_EINK_BUSY, SHARED_MATRIX_BUSY, \
    SHARED_SPEAKER_BUSY, SHARED_LCD_BUSY, SHARED_DSI_LCD_BUSY, SHARED_MICROPHONE_MUTED,\
    SHARED_CHATBOT_BUSY, SHARED_CHATBOT_ANSWER_IS_ERROR, SHARED_IDLE_MODE, SHARED_LCD_IDLE_MODE, \
    SHARED_DSI_LCD_IDLE_MODE, SHARED_NETWORK_BUSY, SHARED_VAD_DETECTED, SHARED_SUPPORT_BUSY, SHARED_STT_BUSY, \
    SHARED_TRANSCRIBER_BUSY, \
    SHARED_MEMORY_VALUES, SHARED_DYNAMIC_RMS_SILENCE_THRESHOLD, SHARED_WAKE_UP_BUTTON_PRESSED, \
    SHARED_SPEAKER_LEVEL, SHARED_FIRST_AUDIO_TIMESTAMP, \
    SHARED_MIC_VOLUME, SHARED_SPEAKER_VOLUME, SHARED_BATTERY_LEVEL, \
    SHARED_SPEAKER_MUTED, SHARED_POWER_CABLE_CONNECTED, \
    SHARED_CPU_TEMPERATURE, SHARED_CPU_FAN_RPM, SHARED_CASE_FAN_1_SPEED, SHARED_CASE_FAN_2_SPEED, \
    SHARED_SPEECH_INTERRUPT_REQUESTED
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.core.doorbell import DoorbellRinger
from pitxu.lib.core.doorbell_waiter import DoorbellWaiter

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
        "transcriber_busy": SHARED_TRANSCRIBER_BUSY,
        "wake_up_button_request": SHARED_WAKE_UP_BUTTON_PRESSED
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
        SHARED_TRANSCRIBER_BUSY: "transcriber_busy",
        SHARED_WAKE_UP_BUTTON_PRESSED: "wake_up_button_request",
        SHARED_SPEECH_INTERRUPT_REQUESTED: "speech_interrupt_requested"
    }
    _shared_values: dict[str, int] = {
        "dynamic_rms_silence_threshold": SHARED_DYNAMIC_RMS_SILENCE_THRESHOLD,
        "speaker_level": SHARED_SPEAKER_LEVEL,
        "first_audio_timestamp": SHARED_FIRST_AUDIO_TIMESTAMP,
        "mic_volume": SHARED_MIC_VOLUME,
        "speaker_volume": SHARED_SPEAKER_VOLUME,
        "battery_level": SHARED_BATTERY_LEVEL,
        "speaker_muted": SHARED_SPEAKER_MUTED,
        "power_cable_connected": SHARED_POWER_CABLE_CONNECTED,
        "cpu_temperature": SHARED_CPU_TEMPERATURE,
        "cpu_fan_rpm": SHARED_CPU_FAN_RPM,
        "case_fan_1_speed": SHARED_CASE_FAN_1_SPEED,
        "case_fan_2_speed": SHARED_CASE_FAN_2_SPEED
    }
    # TODO: consider generating this map automatically together with xprocess_pool, painter_busy_flags, etc.
    _map_index_to_value: dict[int, str] = {
        SHARED_DYNAMIC_RMS_SILENCE_THRESHOLD: "dynamic_rms_silence_threshold",
        SHARED_SPEAKER_LEVEL: "speaker_level",
        SHARED_FIRST_AUDIO_TIMESTAMP: "first_audio_timestamp",
        SHARED_MIC_VOLUME: "mic_volume",
        SHARED_SPEAKER_VOLUME: "speaker_volume",
        SHARED_BATTERY_LEVEL: "battery_level",
        SHARED_SPEAKER_MUTED: "speaker_muted",
        SHARED_POWER_CABLE_CONNECTED: "power_cable_connected",
        SHARED_CPU_TEMPERATURE: "cpu_temperature",
        SHARED_CPU_FAN_RPM: "cpu_fan_rpm",
        SHARED_CASE_FAN_1_SPEED: "case_fan_1_speed",
        SHARED_CASE_FAN_2_SPEED: "case_fan_2_speed"
    }

    # The values that change all the time and that nobody monitors for changes, they are just read when needed
    #   (the speaker level every few milliseconds while speaking, the RMS threshold with every chunk of audio).
    # Ringing the doorbell for them would wake the monitors constantly, which is what the doorbell is meant to avoid.
    _values_that_do_not_ring: set[int] = {
        SHARED_SPEAKER_LEVEL,
        SHARED_DYNAMIC_RMS_SILENCE_THRESHOLD,
    }

    # So a failing doorbell is reported once, not with every write.
    _doorbell_failure_reported: bool = False

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
                False,  # wake up button is pressed
                False,  # speech interrupt requested
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
                0.0,    # speaker level (0.0 - 1.0), drives the speaking animation
                0.0,    # epoch timestamp of the first audio of the current speech, for the latency log
                -1.0,   # microphone volume (%), -1 = unknown
                -1.0,   # speaker volume (%), -1 = unknown
                -1.0,   # battery level (%), -1 = unknown
                -1.0,   # speaker is muted (1 = yes, 0 = no), -1 = unknown
                -1.0,   # power cable is connected (1 = yes, 0 = no), -1 = unknown
                -1.0,   # CPU temperature (Celsius), -1 = unknown
                -1.0,   # CPU fan speed (RPM), -1 = unknown
                -1.0,   # case fan 1 speed (0.0 - 1.0), -1 = no such fan
                -1.0,   # case fan 2 speed (0.0 - 1.0), -1 = no such fan
            ], name=SHARED_MEMORY_VALUES)
        except Exception as e:
            self._xlog.error("Failed to initialize shared memory: " + str(e))
    
    def initialize_existing_shared_memory_values(self):
        self._xlog.info("Loading values from Shared Memory")
        self._shared_memory_values = shared_memory.ShareableList(name=SHARED_MEMORY_VALUES)
        if self._shared_memory_values is None:
            self._xlog.error("Shared Memory is None, cannot read values")

    def attach_shared_memory_values_if_needed(self):
        '''
        Attaches to the existing shared memory values, only if this instance did not do it yet.
        '''
        if self._shared_memory_values is None:
            self.initialize_existing_shared_memory_values()
    
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
        previous = self._shared_memory_flags[index]
        self._shared_memory_flags[index] = value
        # The monitors sleep until something changes: tell them. Only a change, writing the same value is not news.
        if previous != value:
            self._ring_the_doorbell()
    
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
        if index in self._values_that_do_not_ring:
            self._shared_memory_values[index] = value
            return
        previous = self._shared_memory_values[index]
        self._shared_memory_values[index] = value
        if previous != value:
            self._ring_the_doorbell()

    def _ring_the_doorbell(self):
        """
        Tells the monitors that the shared memory changed, so they check it now instead of at their next poll.
        """
        # ⚠️ This is called from everywhere, including the audio callback: whatever happens here must never reach the writer,
        #   as the audio library aborts the input stream when its callback raises.
        try:
            ringer = DoorbellRinger.get()
            if ringer is not None:
                ringer.ring()
        except Exception as e:
            if not self._doorbell_failure_reported:
                self._doorbell_failure_reported = True
                self._xlog.warning(f"🔔 The doorbell failed, the monitors will rely on their safety timeout: {type(e).__name__}: {e}")
    
    def wait_for_all_busy_process_to_idle(self, wait_forever: bool = True):
        # Now wait until the displays finish being busy
        self._xlog.debug("Waiting for all processes to get idle")
        self.log_summary(
            "Current processes busy flags", 
            [(name, "BUSY" if self.read_shared_memory_flag(flag) else "IDLE") for name, flag in self._shared_flags.items()])
        start_time = time.monotonic()
        idle = DoorbellWaiter.wait_until(
            lambda: not any(self.read_shared_memory_flag(flag) for flag in self._shared_flags.values()),
            timeout=None if wait_forever else self.WAITING_FOR_QUEUES_TIMEOUT_SECONDS,
            polling_seconds=self.WAITING_SLEEP_SECONDS)
        waited = round(time.monotonic() - start_time, 3)
        if idle:
            self._xlog.debug(f"All processes are idle now. I've waited {waited}s.")
        else:
            self._xlog.error("Timeout reached while waiting for all processes to idle.")
            self._xlog.debug(f"Forced break after waiting for {waited}s for all processes to idle.")
    
    def wait_for_busy_process_to_idle(self, memory_position: int, wait_forever: bool = True):
        memory_position_name = self._map_index_to_flag.get(memory_position, "unknown")
        self._xlog.debug(f"Waiting for the process {memory_position_name} to idle. It's now: " + ("BUSY" if self.read_shared_memory_flag(memory_position) else "IDLE") + ".")
        start_time = time.monotonic()
        idle = DoorbellWaiter.wait_until(
            lambda: not self.read_shared_memory_flag(memory_position),
            timeout=None if wait_forever else self.WAITING_FOR_QUEUES_TIMEOUT_SECONDS,
            polling_seconds=self.WAITING_SLEEP_SECONDS)
        waited = round(time.monotonic() - start_time, 3)
        if idle:
            self._xlog.debug(f"The process {memory_position_name} is idle now. I've waited {waited}s.")
        else:
            self._xlog.error(f"Timeout reached while waiting for process {memory_position_name} to idle.")
            self._xlog.debug(f"Forced break after waiting for {waited}s for process {memory_position_name} to idle.")
    
    def wait_for_busy_process_to_be_busy(self, memory_position: int):
        memory_position_name = self._map_index_to_flag.get(memory_position, "unknown")
        self._xlog.debug(f"Waiting for the process {memory_position_name} to be busy. It's now: " + ("BUSY" if self.read_shared_memory_flag(memory_position) else "IDLE") + ".")
        start_time = time.monotonic()
        DoorbellWaiter.wait_until(
            lambda: bool(self.read_shared_memory_flag(memory_position)),
            polling_seconds=self.WAITING_SLEEP_SECONDS)
        self._xlog.debug(f"The process {memory_position_name} is busy now. I've waited {round(time.monotonic() - start_time, 3)}s.")
    
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
    

