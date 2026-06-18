import re

from pyxavi import Config, Dictionary
from definitions import SHARED_DSI_LCD_IDLE_MODE
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager

import threading
import time

class PainterSharedMemory(PyXavi):

    _worker_thread: threading.Thread = None

    _shared_memory: SharedMemoryManager = None
    _shared_memory_flag_to_callback: list[tuple[int, bool, callable]] = None
    _shared_memory_flag_previous_value: dict[int, bool] = None

    # We need to be able to resume the painter, whenever we trigger a callback from the shared memory control worker, 
    #   to ensure that the interaction is painted as soon as possible.
    _painter_resume_callback: callable = None

    THREAD_NAME: str = "PainterSharedMemory"

    is_active: bool = True

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config, params: Dictionary):
        super(PainterSharedMemory, self).init_pyxavi(config, params)

        if params.key_exists("shared_memory"):
            self._xlog.debug("Using provided shared memory manager for PainterBusyFlags.")
            self.shared_memory = params.get("shared_memory")
        else:
            self._xlog.debug("Using existing initialized shared memory manager for PainterBusyFlags.")
            self.shared_memory = SharedMemoryManager(config=config)
            self.shared_memory.initialize_existing_shared_memory_flags()
        
        if params.key_exists("painter_resume_callback"):
            self._xlog.debug("Using provided painter resume callback for PainterSharedMemory.")
            self._painter_resume_callback = params.get("painter_resume_callback")
        else:
            raise ValueError("PainterSharedMemory requires a painter_resume_callback to be provided in the params. Got None.")
        
        # Initialize the list of shared memory flags to control, empty otherwise.
        shared_memory_list_to_control = params.get("shared_memory_list_to_control", [])
        self.load_list_control(shared_memory_list_to_control)
        
        # We control the transitions of the shared_memory flags and values in a separate thread.
        self._worker_thread = threading.Thread(
            name=self.THREAD_NAME,
            target=self._shared_memory_control_worker,
            daemon=True)
        self.start_monitoring_shared_memory()
    
    def load_list_control(self, shared_memory_list_to_control: list[tuple[int, bool, callable]]):
        for shared_memory_flag, activation_value, callback in shared_memory_list_to_control:
            if not isinstance(shared_memory_flag, int):
                raise ValueError(f"Shared memory flag must be an integer. Got {type(shared_memory_flag)}.")
            if shared_memory_flag not in self.shared_memory._map_index_to_flag:
                raise ValueError(f"Invalid received shared memory flag: {self.get_shared_memory_flag_name_for(shared_memory_flag)}.")
            if not callable(callback):
                raise ValueError(f"Callback must be callable. Got {type(callback)}.")
            if not isinstance(activation_value, bool):
                raise ValueError(f"Activation value must be a boolean. Got {type(activation_value)}.")
        
        self._shared_memory_flag_to_callback = shared_memory_list_to_control
    
    def start_monitoring_shared_memory(self):
        if self._shared_memory_flag_to_callback is None:
            raise ValueError("No shared memory flags to control. Please set the list of shared memory flags to control using the 'load_list_control' method.")
        
        self.is_active = True
        self._worker_thread.start()
    
    def shutdown(self):
        self._xlog.debug("Shutting down PainterSharedMemory.")
        self.is_active = False
    
    def close(self):
        self.shutdown()

        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._xlog.debug("Joining shared memory control worker thread.")
            self._worker_thread.join(timeout=2)
            if self._worker_thread.is_alive():
                self._xlog.warning("Shared memory control worker thread did not finish in time.")
            else:
                self._xlog.debug("Shared memory control worker thread finished successfully.")
        else:
            self._xlog.debug("Shared memory control worker thread is not alive or was never started.")
    
    def set_callback_for_shared_memory_flag(self, name: str, shared_memory_flag: int, activation_value: bool, callback: callable, is_dependant: bool = False):
        if shared_memory_flag not in self.shared_memory._map_index_to_flag:
            raise ValueError(f"Invalid received shared memory flag: {self.get_shared_memory_flag_name_for(shared_memory_flag)}.")
        if not isinstance(activation_value, bool):
            raise ValueError(f"Activation value must be a boolean. Got {type(activation_value)}.")
        if not callable(callback):
            raise ValueError(f"Callback must be callable. Got {type(callback)}.")
        
        if self._shared_memory_flag_to_callback is None:
            self._shared_memory_flag_to_callback = []
        
        # We check if the flag is already in the list with the existing activation value, and if so, we update the callback.
        updated_existing_flag = False
        for i, (existing_name, flag, existing_activation_value, existing_callback, existing_is_dependant) in enumerate(self._shared_memory_flag_to_callback):
            if flag == shared_memory_flag and existing_activation_value == activation_value and existing_name == name:
                self._shared_memory_flag_to_callback[i] = (name, shared_memory_flag, activation_value, callback, is_dependant)
                updated_existing_flag = True
                break
        
        # Now, if we did NOT update an existing flag, means that we need to set up the environment for the worker
        # to be able to detect the transition to the activation value for this flag, when it is activated.
        if not updated_existing_flag:

            # The worker monitors value transitions.
            # To be able to control it, we need to get the current value of the flag and set it as the previous value, 
            # so we can detect the transition to the activation value in the worker.
            # It needs to happen BEFORE we add the flag to the list, 
            # otherwise the worker may detect a transition to the activation value before we have set the previous value, 
            # which would lead to a wrong callback call.
            # current_value = self.shared_memory.read_shared_memory_flag(shared_memory_flag)
            if self._shared_memory_flag_previous_value is None:
                self._shared_memory_flag_previous_value = {}
            # Could be that we add a monitoring for a flag that is already active.
            # The previous value will be the same of the activation, so the worker won't detect a transition.
            # That's why we initialize the previous value with with a None, so the worker will be forced to detect
            # the first transition to the activation value, even if the flag is already at that value.
            # self._shared_memory_flag_previous_value[shared_memory_flag] = current_value
            self._shared_memory_flag_previous_value[shared_memory_flag] = None
        
            # If the flag is not in the list, we add it.
            self._shared_memory_flag_to_callback.append((name, shared_memory_flag, activation_value, callback, is_dependant))
    
    def remove_callback_for_shared_memory_flag(self, name: str, shared_memory_flag: int, activation_value: bool):
        if self._shared_memory_flag_to_callback is None:
            return
        
        self._shared_memory_flag_to_callback = [
            (existing_name, flag, existing_activation_value, existing_callback, is_dependant)
                for existing_name, flag, existing_activation_value, existing_callback, is_dependant in self._shared_memory_flag_to_callback
                    if not (flag == shared_memory_flag and existing_activation_value == activation_value and existing_name == name)
        ]
    
    def get_shared_memory_flags_current_status(self) -> list[tuple[str, int, str, bool, bool, str, bool]]:
        """
        Just a helper to get the expected and current status of the shared memory flags.
        """
        if self._shared_memory_flag_to_callback is None:
            return []
        
        result = []
        for name, flag, activation_value, callback, is_dependant in self._shared_memory_flag_to_callback:
            result.append((
                name,
                flag, 
                self.get_shared_memory_flag_name_for(flag), 
                activation_value, 
                self.shared_memory.read_shared_memory_flag(flag),
                callback.__name__ if callable(callback) else str(callback),
                is_dependant
            ))
        return result
    
    def did_shared_memory_flag_change_to_activation_value(self, shared_memory_flag: int, activation_value: bool, is_dependant: bool) -> bool:
        current_value = self.shared_memory.read_shared_memory_flag(shared_memory_flag)
        previous_value = self._shared_memory_flag_previous_value.get(shared_memory_flag, None)
        # return previous_value is not None and current_value != previous_value and current_value == activation_value
        if previous_value is None and current_value == activation_value and not is_dependant:
            self._log_debug(f"🏳️  Shared memory flag {self.get_shared_memory_flag_name_for(shared_memory_flag)} is being monitored for the value {activation_value}, and it has no previous value, but the current value is already at the activation value. Will consider that it changed to the activation value.")
            return True
        elif previous_value is not None and current_value != previous_value and current_value == activation_value:
            self._log_debug(f"🏳️  Shared memory flag {self.get_shared_memory_flag_name_for(shared_memory_flag)} is being monitored for the value {activation_value}, and it changed from {previous_value} to {current_value}.")
            return True
        else:
            return False
    
    def did_previous_callback_to_dependant_ran_already(self, name: str, shared_memory_flag: int, activation_value: bool) -> bool:
        """
        This is a helper to control the execution of dependant callbacks. 
        It checks if the callback that is supposed to run before the dependant one has already been ran,
            by checking if the actual previous callback is still there (when we run a callback, we de-register it).
            So, it should NOT be there anymore if it has already been ran.
        Note that the previous callback is always attached to the same flag and the opposite activation value.
        """
        if self._shared_memory_flag_to_callback is None:
            # This should not happen, because if we have a dependant callback, 
            # it means that we have already added the previous callback to the list, 
            # but we add this check just in case, and if so it should return True 
            # (no previous callback, so it ran).
            return True
        
        # If the previous callback is still in the list, it means that it has not been ran yet, so we return False.
        for existing_name, flag, existing_activation_value, existing_callback, is_dependant in self._shared_memory_flag_to_callback:
            if name == existing_name and \
                flag == shared_memory_flag and \
                existing_activation_value == (not activation_value) and \
                not is_dependant:
                
                return False
        
        # Still here? No previous related callback found, then it ran.
        return True
        
    
    def update_shared_memory_flag_monitored_previous_value(self, shared_memory_flag: int):
        current_value = self.shared_memory.read_shared_memory_flag(shared_memory_flag)
        self._shared_memory_flag_previous_value[shared_memory_flag] = current_value
    
    def trigger_callback_for_shared_memory_flag(self, name: str, shared_memory_flag: int, activation_value: bool):
        for existing_name, flag, expected_activation_value, callback, is_dependant in self._shared_memory_flag_to_callback:
            # # First, if the previous value is None, means that we just added this flag to the monitoring list, 
            # # so we consider that it has changed to the activation value, so we trigger the callback
            # #   if the rest of the parameters match (name, flag, activation_value).
            # if self._shared_memory_flag_previous_value.get(shared_memory_flag, None) is None and \
            #     existing_name == name and flag == shared_memory_flag:
            #         callback()
            # # The previous value has an actual value, so we check the proper transition.
            # elif existing_name == name and flag == shared_memory_flag and expected_activation_value == activation_value:
            #     callback()
            if existing_name == name and flag == shared_memory_flag and expected_activation_value == activation_value:
                callback()
    
    def get_shared_memory_manager(self) -> SharedMemoryManager:
        return self.shared_memory
    
    def get_shared_memory_flag_name_for(self, shared_memory_flag: int) -> str:
        return self.shared_memory._map_index_to_flag.get(shared_memory_flag, f"UnknownFlag_{shared_memory_flag}").upper()
    
    def _shared_memory_control_worker(self):
        """
        This worker will control the transitions of the shared_memory flags and values.
        It will check the flags in the _shared_memory_list_to_control list and call the corresponding callbacks when the flags change.
        """

        while self.is_active:
            if self._shared_memory_flag_to_callback is not None:

                # We first need to collect all the possible callbacks to trigger,
                #   AND THEN trigger them,
                #   AND THEN update the previous value of the flags.
                # If we don't do it this way, the first callback already updates the value and 
                #   other possible callbacks for the same flag and value won't be triggered.
                callbacks_to_trigger = []
                for name, shared_memory_flag, activation_value, callback, is_dependant in self._shared_memory_flag_to_callback:

                    # Did the flag change to anything we're monitoring?
                    if self.did_shared_memory_flag_change_to_activation_value(shared_memory_flag, activation_value, is_dependant):

                        # Are we checking a dependant callback? If so, did the previous one already ran?
                        if is_dependant and not self.did_previous_callback_to_dependant_ran_already(name, shared_memory_flag, activation_value):
                            self._log_debug(f"🏳️  Dependant callback for shared memory flag {self.get_shared_memory_flag_name_for(shared_memory_flag)} and value {activation_value} is waiting for the previous callback to run.")
                        else:

                            # The flag changed to the value we're monitoring, so we call the callback.
                            self._log_debug(f"🏳️  Shared memory flag {self.get_shared_memory_flag_name_for(shared_memory_flag)} changed to the value {activation_value}. Will call [{name}].")
                            callbacks_to_trigger.append((name, shared_memory_flag, activation_value, callback))

                # Now we trigger the callbacks that we collected.
                for name, shared_memory_flag, activation_value, callback in callbacks_to_trigger:
                    self._log_debug(f"🏳️  Triggering callback [{name}] for the flag {self.get_shared_memory_flag_name_for(shared_memory_flag)} at value {activation_value}.")
                    self.trigger_callback_for_shared_memory_flag(name, shared_memory_flag, activation_value)
                
                # Finally, we update the previous value of the flags that changed, to be able to detect future changes.
                for _, shared_memory_flag, _, _ in callbacks_to_trigger:
                    self._log_debug(f"🏳️  Updating previous value for shared memory flag {self.get_shared_memory_flag_name_for(shared_memory_flag)} after triggering callbacks.")
                    self.update_shared_memory_flag_monitored_previous_value(shared_memory_flag)
                
                # If we had any callback to trigger, we need to ensure that we resume the painter loop.
                # 2. Resume the painter loop in case it was paused, to ensure that the interaction is painted as soon as possible.
                if callbacks_to_trigger:
                    self._log_debug(f"🏳️  Resuming painter loop after triggering callbacks for shared memory flags.")
                    self._painter_resume_callback()

            # If we're in idle mode, we can afford to check the shared memory less often, to reduce CPU usage, 
            # because we know that there won't be any interaction to paint, so we don't need to trigger the callbacks as soon as possible.
            if self.shared_memory.read_shared_memory_flag(SHARED_DSI_LCD_IDLE_MODE):
                time.sleep(1)
            else:
                time.sleep(0.2)

    def is_idle_mode_on(self) -> bool:
        return self.shared_memory.read_shared_memory_flag(SHARED_DSI_LCD_IDLE_MODE)