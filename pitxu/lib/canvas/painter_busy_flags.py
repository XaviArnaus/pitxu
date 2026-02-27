from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from pitxu.lib.canvas.paint_objects import BackgroundPaint, ForegroundPaint

from definitions import FOREGROUND_CHANNEL, BACKGROUND_CHANNEL, LOOP_START, LOOP_END,\
                        SHARED_SPEAKER_BUSY, SHARED_EINK_BUSY, SHARED_MATRIX_BUSY, SHARED_LCD_BUSY, SHARED_DSI_LCD_BUSY, SHARED_CHATBOT_BUSY, SHARED_COMMUNICATION_BUSY

class PainterBusyFlags(PyXavi):

    # TODO: consider generating these lists automatically together with shared_memory_manager, xprocess_pool, etc.

    AVAILABLE_CHANNELS = [
        FOREGROUND_CHANNEL,
        BACKGROUND_CHANNEL
    ]

    AVAILABLE_WHEN = [
        LOOP_START,
        LOOP_END
    ]

    AVAILABLE_BUSY_FLAGS = [
        SHARED_SPEAKER_BUSY,
        SHARED_EINK_BUSY,
        SHARED_MATRIX_BUSY,
        SHARED_LCD_BUSY,
        SHARED_DSI_LCD_BUSY,
        SHARED_CHATBOT_BUSY,
        SHARED_COMMUNICATION_BUSY
    ]

    MANDATORY_FULL_CYCLE_BUSY_FLAGS = [
        SHARED_SPEAKER_BUSY,
        SHARED_CHATBOT_BUSY,
        SHARED_COMMUNICATION_BUSY
    ]

    VERBOSE_DEBUG: bool = False

    registered_callbacks: dict = {}
    shared_memory: SharedMemoryManager = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(PainterBusyFlags, self).init_pyxavi(config=config, params=params)

        if params.key_exists("shared_memory"):
            self._xlog.debug("Using provided shared memory manager for PainterBusyFlags.")
            self.shared_memory = params.get("shared_memory")
        else:
            self._xlog.debug("Creating new shared memory manager for PainterBusyFlags.")
            self.shared_memory = SharedMemoryManager(config=config)
            self.shared_memory.initialize_existing_shared_memory_flags()

    def is_valid(self, when: str, channel: str, flag_name: int) -> bool:
        result = when in self.AVAILABLE_WHEN and channel in self.AVAILABLE_CHANNELS and flag_name in self.AVAILABLE_BUSY_FLAGS
        # self._log_debug(f"Validating busy flag combination [{when}, {channel}, {self._flag_string(flag_name)}]: {result}.")
        return result
    
    def set_busy_flag_callback(self, when: str, channel: str, flag_name: int, for_value: bool, callback: callable):
        self._log_debug(f"Setting busy flag callback for flag [{self._flag_string(flag_name)}] with value [{for_value}] in channel [{channel}] at [{when}].")
        if self.is_valid(when, channel, flag_name):
            if when not in self.registered_callbacks:
                self.registered_callbacks[when] = {}
            if channel not in self.registered_callbacks[when]:
                self.registered_callbacks[when][channel] = {}
            if str(flag_name) not in self.registered_callbacks[when][channel]:
                self.registered_callbacks[when][channel][str(flag_name)] = [None, None]  # Index 0 for False, Index 1 for True
            self.registered_callbacks[when][channel][str(flag_name)][int(for_value)] = callback
        else:
            self._xlog.error(f"🛑 Trying to set busy flag callback for unknown combination [{when}, {channel}, {self._flag_string(flag_name)}, {for_value}]")
            raise ValueError(f"Trying to set busy flag callback for unknown combination [{when}, {channel}, {self._flag_string(flag_name)}, {for_value}].")
    
    def remove_busy_flag_callback(self, when: str, channel: str, flag_name: int, for_value: bool):
        self._log_debug(f"Removing busy flag callback for flag [{self._flag_string(flag_name)}] with value [{for_value}] in channel [{channel}] at [{when}].")
        if self.is_valid(when, channel, flag_name):
            # If the starting callback is still there, means that is not yet triggered, so we don't want to remove it.
            # Why is trigered the END before the START? 
            #   Maybe the interaction is added while painting, betwen START and END,
            #   so the END of the interation [n] is called before the START of [n+1]?
            # Smells like race condition, so we block it.
            # We don't do it in Background because we want to have the ability to stop background paintings whenever needed.
            if self._is_end_callback_with_start_still_registered(when=when, channel=channel, flag_name=flag_name):
                self._log_debug(f"🛑 Callback for flag [{self._flag_string(flag_name)}] in channel [{channel}] at [{when}] cannot be removed now because a start callback for speaker busy is still registered. Skipping.")
            else:
                self.registered_callbacks[when][channel][str(flag_name)][int(for_value)] = None
        else:
            self._xlog.error(f"🛑 Trying to remove busy flag callback for unknown combination [{when}, {channel}, {self._flag_string(flag_name)}, {for_value}]")
            raise ValueError(f"Trying to remove busy flag callback for unknown combination [{when}, {channel}, {self._flag_string(flag_name)}, {for_value}].")
    
    def _is_end_callback_with_start_still_registered(self, when: str, channel: str, flag_name: int) -> bool:
        if when == LOOP_END:
            for value in [True, False]:
                # Check if the start callback is still registered for the given 
                if self.callback_exists_for_busy_flag(when=LOOP_START, channel=channel, flag_name=flag_name, for_value=value):
                    return True
        return False
    
    def callback_exists_for_busy_flag(self, when: str, channel: str, flag_name: int, for_value: bool) -> bool:
        if self.is_valid(when, channel, flag_name):
            if when not in self.registered_callbacks:
                # self._xlog.debug(f"No busy flag callback registered at [{when}].")
                return False
            if channel not in self.registered_callbacks[when]:
                # self._xlog.debug(f"No busy flag callback registered at [{when}] in channel [{channel}].")
                return False
            if str(flag_name) not in self.registered_callbacks[when][channel]:
                # self._xlog.debug(f"No busy flag callback registered at [{when}] in channel [{channel}] for flag [{self._flag_string(flag_name)}].")
                return False
            if self.registered_callbacks[when][channel][str(flag_name)][int(for_value)] is None:
                # self._xlog.debug(f"No busy flag callback registered at [{when}] in channel [{channel}] for flag [{self._flag_string(flag_name)}] with value [{for_value}].")
                return False
            return True
        else:
            self._xlog.error(f"🛑 Trying to check busy flag callback for unknown combination [{when}, {channel}, {self._flag_string(flag_name)}, {for_value}({int(for_value)})]")
            raise ValueError(f"Trying to check busy flag callback for unknown combination [{when}, {channel}, {self._flag_string(flag_name)}, {for_value}({int(for_value)})].")

    def call_busy_flag_callback(self, when: str, channel: str, flag_name: int, value: any) -> dict:
        self._log_debug(f"Intending to call busy flag callback for flag [{self._flag_string(flag_name)}] with value [{value}] in channel [{channel}] at [{when}].")
        # Safety checks for mandatory full cycle busy flags.
        # We need to check for the corresponding START/END callback to be registered/unregistered.
        # this also applies to the value being set, because we work with flags, the opposite event also has the opposite value.
        if flag_name in self.MANDATORY_FULL_CYCLE_BUSY_FLAGS:
            if when == LOOP_START and not self.callback_exists_for_busy_flag(when=LOOP_END, channel=channel, flag_name=flag_name, for_value=(not value)):
                self._log_debug(f"🟠 Trying to call busy flag callback for [{self._flag_string(flag_name)}] with value [{value}] in channel [{channel}] at [{when}], but the corresponding END callback is not registered. Full cycle mandatory.")
                return
            if when == LOOP_END and self.callback_exists_for_busy_flag(when=LOOP_START, channel=channel, flag_name=flag_name, for_value=(not value)):
                self._log_debug(f"🟠 Trying to call busy flag callback for [{self._flag_string(flag_name)}] with value [{value}] in channel [{channel}] at [{when}], but the corresponding START callback is still registered. Full cycle mandatory.")
                return

        self._log_debug(f"Calling busy flag callback for flag [{self._flag_string(flag_name)}] with value [{value}] in channel [{channel}] at [{when}].")
        if self.callback_exists_for_busy_flag(when, channel, flag_name, value):
            callback = self.registered_callbacks[when][channel][str(flag_name)][int(value)]
            if callback is not None:
                # Trigger the callback
                self._log_debug(f"Calling busy flag callback now.")
                # The callback is expected to return a dict with any relevant information.
                return callback()
        else:
            self._xlog.error(f"🛑 Trying to call busy flag callback for unknown flag [{when}, {channel}, {self._flag_string(flag_name)}, {value}({int(value)})].")
            dd(self.registered_callbacks)
            raise ValueError(f"Trying to call busy flag callback for unknown flag [{when}, {channel}, {self._flag_string(flag_name)}, {value}({int(value)})].")
    
    def call_monitoring_busy_flags_callbacks(self, when: str) -> list:
        if when not in self.AVAILABLE_WHEN:
            self._xlog.error(f"🛑 Trying to set busy flag callback for unknown when [{when}].")
            raise ValueError(f"Trying to set busy flag callback for unknown when [{when}].")
        
        while True:
            try:
                callback_returns = []
                for channel in self.AVAILABLE_CHANNELS:
                    if when in self.registered_callbacks and channel in self.registered_callbacks[when]:
                        for flag_name, callback in self.registered_callbacks[when][channel].items():
                                flag_value = self.shared_memory.read_shared_memory_flag(int(flag_name))
                                if callback[int(flag_value)] is not None:
                                    
                                    # We have a callback
                                    callback_result = self.call_busy_flag_callback(when, channel, int(flag_name), flag_value)
                                    if callback_result is not None:
                                        callback_returns.append(callback_result)

                return callback_returns
            except RuntimeError as e:
                # I've found scenarios where the self.registered_callbacks loop can raise RuntimeError: dictionary changed size during iteration.
                # This is likely due to a callback modifying the registered_callbacks, which is not ideal
                #  but we can safely ignore it for now.
                # Idea here is to catch the exception, then the iteration will continue, and the return will break the while True loop.
                pass

    def trigger_busy_flags_callbacks_at_loop_start(self) -> list:
        return self.call_monitoring_busy_flags_callbacks(when=LOOP_START)

    def trigger_busy_flags_callbacks_at_loop_end(self) -> list:
        return self.call_monitoring_busy_flags_callbacks(when=LOOP_END)

    def _flag_string(self, flag_name: int) -> str:
        return self.shared_memory._map_index_to_flag[flag_name] + f"({flag_name})"

    def get_registered_callbacks_list(self, when: str = None) -> list:
        result = []
        when_keys = [when] if when is not None else self.registered_callbacks.keys()
        for when_key in when_keys:
            if when_key in self.registered_callbacks:
                for channel, flags in self.registered_callbacks[when_key].items():
                    for flag_name, callbacks in flags.items():
                        for value_index, callback in enumerate(callbacks):
                            if callback is not None:
                                result.append(f"({when_key}, {channel}, {self._flag_string(int(flag_name))}, {bool(value_index)})")
                                # result.append({
                                #     "when": when_key,
                                #     "channel": channel,
                                #     "flag_name": int(flag_name),
                                #     "for_value": bool(value_index),
                                #     "callback": callback
                                # })
        return result