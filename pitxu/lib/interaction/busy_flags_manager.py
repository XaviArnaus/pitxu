from __future__ import annotations
from threading import Thread
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
import time

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

from definitions import SHARED_SPEAKER_BUSY, SHARED_EINK_BUSY, SHARED_CHATBOT_BUSY, SHARED_MATRIX_BUSY, SHARED_LCD_BUSY

class BusyFlagsManager(PyXavi, Thread):
    """
    Manages the busy flags for different components in the system.

    The idea is good, but this class is not yet used in the system.
    What we have is a simpler version focused on displays in canvas/painter_busy_flags.py.
    """

    shared_memory: SharedMemoryManager = None

    STATE_SPEAKER = "speaker_busy"
    STATE_EINK = "eink_busy"
    STATE_CHATBOT = "chatbot_busy"
    STATE_MATRIX = "matrix_busy"
    STATE_LCD = "lcd_busy"

    state = {
        STATE_SPEAKER: False,
        STATE_EINK: False,
        STATE_CHATBOT: False,
        STATE_MATRIX: False,
        STATE_LCD: False
    }

    busy_flags_callback: callable = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(BusyFlagsManager, self).init_pyxavi(config=config, params=params)

        self._shared_memory = SharedMemoryManager(config=config, params=params)
        self._shared_memory.initialize_existing_shared_memory_flags()

        if self._xparams.get("busy_flags_callback") is None:
            self._xlog.error("No busy_flags_callback defined in params. BusyFlagsManager will not notify on changes.")
            return
        else:
            self.busy_flags_callback = self._xparams.get("busy_flags_callback")

        self.state = self._read_flags()

        Thread.__init__(self, name="BusyFlags", daemon=True)
    
    def start_listening_flag_changes(self):
        self._xlog.debug("Starting to listen for busy flag changes.")
        self.running = True
        self.start()

    def run(self):
        while self.running:
            
            current_flags = self._read_flags()
            for state_name, new_value in current_flags.items():
                if self.flag_changed(state_name, new_value):
                    self._xlog.debug(f"Flag changed: {state_name} = {new_value}")
                    self.update_flag(state_name, new_value)
                    # Call the callback to notify about the change
                    self.busy_flags_callback(state_name, new_value)

            time.sleep(0.1)
        
    def stop(self):
        self.running = False
    
    def close(self):
        self._xlog.debug("Closing BusyFlagsManager.")
        self.stop()
        self.join()
        
    def _read_flags(self):
        return {
            self.STATE_SPEAKER: self._shared_memory.read_shared_memory_flag(SHARED_SPEAKER_BUSY),
            self.STATE_EINK: self._shared_memory.read_shared_memory_flag(SHARED_EINK_BUSY),
            self.STATE_CHATBOT: self._shared_memory.read_shared_memory_flag(SHARED_CHATBOT_BUSY),
            self.STATE_MATRIX: self._shared_memory.read_shared_memory_flag(SHARED_MATRIX_BUSY),
            self.STATE_LCD: self._shared_memory.read_shared_memory_flag(SHARED_LCD_BUSY)
        }

    def flag_changed(self, state_name: str, new_value: bool) -> bool:
        return self.state.get(state_name, None) != new_value

    def update_flag(self, state_name: str, new_value: bool):
        self.state[state_name] = new_value