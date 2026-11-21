
from pyxavi import Config, Dictionary
from definitions import SHARED_DSI_LCD_IDLE_MODE
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.core.shared_memory_manager import SharedMemoryManager
from pitxu.lib.core.doorbell import Doorbell, DoorbellListener

import threading
import time

class SharedMemoryMonitor(PyXavi):
    """
    This class monitors ALL shared memory flags and values and calls the corresponding callbacks when
    the flags change to the expected values, or the values change, if there's anything registered over them.

    It is the only implementation of this monitoring. The Painter one (PainterSharedMemory) is a subclass
    that only adds the resuming of the painter loop through the _after_callbacks_triggered() hook.

    The flags are registered as (name, flag, activation value, callback, is dependant) tuples.
    """

    _worker_thread: threading.Thread = None

    _shared_memory: SharedMemoryManager = None
    _shared_memory_flag_to_callback: list[tuple[str, int, bool, callable, bool]] = None
    _shared_memory_flag_previous_value: dict[int, bool] = None
    _shared_memory_value_to_callback: list[tuple[str, int, callable]] = None
    _shared_memory_value_previous: dict[int, float] = None

    THREAD_NAME: str = "SharedMemoryMonitor"

    # The doorbell that the writers ring when something changes in the shared memory (see Doorbell).
    # The worker sleeps until it is rung, instead of waking up every few milliseconds to check.
    # None means no doorbell: the worker polls like it always did.
    BELL_NAME: str | None = Doorbell.BELL_MAIN_MONITOR
    # Even if it is not rung, the worker checks the shared memory at least this often.
    # It is a safety net for a ring that never arrives, so the changes are not left unattended for long.
    SAFETY_TIMEOUT_SECONDS: float = 1.0
    # When it polls (no doorbell), how often. Slower in idle mode, as nothing is going to be painted.
    POLLING_SECONDS: float = 0.2
    POLLING_IDLE_SECONDS: float = 1.0

    is_active: bool = True

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config, params: Dictionary):
        super(SharedMemoryMonitor, self).init_pyxavi(config, params)

        self._xlog.info(f"Initialising {self.__class__.__name__}")

        if params.key_exists("shared_memory"):
            self._xlog.debug(f"Using provided shared memory manager for {self.__class__.__name__}.")
            self.shared_memory = params.get("shared_memory")
        else:
            self._xlog.debug(f"Using existing initialized shared memory manager for {self.__class__.__name__}.")
            self.shared_memory = SharedMemoryManager(config=config)
            self.shared_memory.initialize_existing_shared_memory_flags()

        # The flags and values to monitor, and the last value seen for each.
        self._shared_memory_flag_to_callback = []
        self._shared_memory_flag_previous_value = {}
        self._shared_memory_value_to_callback = []
        self._shared_memory_value_previous = {}

        # Initialize the list of shared memory flags to control, empty otherwise.
        shared_memory_list_to_control = params.get("shared_memory_list_to_control", [])
        self.load_list_control(shared_memory_list_to_control)

        # The doorbell is bound BEFORE the worker reads anything, so a change that happens in between is not missed.
        self._doorbell = self._create_doorbell_listener()
        # Numbers for the closing log: how much the worker woke up, and why.
        self._stats = {"passes": 0, "rung": 0, "timeouts": 0, "polls": 0}

        # We control the transitions of the shared_memory flags and values in a separate thread.
        self._worker_thread = threading.Thread(
            name=self.THREAD_NAME,
            target=self._shared_memory_control_worker,
            daemon=True)
        self.start_monitoring_shared_memory()
    
    def load_list_control(self, shared_memory_list_to_control: list[tuple[str, int, bool, callable, bool]]):
        for name, shared_memory_flag, activation_value, callback, is_dependant in shared_memory_list_to_control:
            self.set_callback_for_shared_memory_flag(name, shared_memory_flag, activation_value, callback, is_dependant)
    
    def start_monitoring_shared_memory(self):
        if self._shared_memory_flag_to_callback is None:
            raise ValueError("No shared memory flags to control. Please set the list of shared memory flags to control using the 'load_list_control' method.")
        
        self.is_active = True
        self._worker_thread.start()
    
    def _create_doorbell_listener(self) -> DoorbellListener | None:
        """
        Binds the doorbell of this monitor. If it can not be done, the worker polls, like it always did.
        """
        if self.BELL_NAME is None or not Doorbell.is_enabled("monitors"):
            self._xlog.info(f"🔔 Doorbell OFF for {self.__class__.__name__}: it polls the shared memory (config doorbell.enabled / doorbell.monitors).")
            return None
        try:
            listener = DoorbellListener(self.BELL_NAME)
            self._xlog.info(f"🔔 Doorbell ON for {self.__class__.__name__}: listening at {Doorbell.path_for(self.BELL_NAME)}")
            return listener
        except OSError as e:
            self._xlog.warning(f"Could not bind the doorbell [{self.BELL_NAME}], {self.__class__.__name__} will poll the shared memory: {e}")
            return None

    def shutdown(self):
        self._xlog.debug(f"Shutting down {self.__class__.__name__}.")
        self.is_active = False
        # The worker may be sleeping until the next ring: ring it ourselves, so it sees that it has to leave.
        if self._doorbell is not None:
            self._doorbell.wake()

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

        # The worker is not using it any more.
        if self._doorbell is not None:
            self._doorbell.close()
            self._doorbell = None

    def get_stats(self) -> dict[str, int]:
        """
        How many times the worker checked the shared memory, and what woke it up: a ring, the safety timeout or the polling.
        """
        return dict(self._stats)
    
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
                getattr(callback, "__name__", repr(callback)),
                is_dependant
            ))
        return result
    
    def did_shared_memory_flag_change_to_activation_value(
        self, shared_memory_flag: int, activation_value: bool, is_dependant: bool, current_value: bool | None = None
    ) -> bool:
        # The worker passes the value it sampled at the start of the pass, so every decision of the pass is based on the same one.
        if current_value is None:
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
    
    def set_callback_for_shared_memory_value(self, name: str, shared_memory_value: int, callback: callable):
        """
        Registers a callback that runs whenever the given shared memory value changes.
        The first time the value is seen counts as a change, so the callback also runs once to sync the initial state.
        Values are compared exactly, so publish integers if you don't want noise.
        """
        if shared_memory_value not in self.shared_memory._map_index_to_value:
            raise ValueError(f"Invalid received shared memory value index: {shared_memory_value}.")
        if not callable(callback):
            raise ValueError(f"Callback must be callable. Got {type(callback)}.")

        # The display process attaches to the values only when it needs them.
        self.shared_memory.attach_shared_memory_values_if_needed()

        self._shared_memory_value_to_callback.append((name, shared_memory_value, callback))

    def _check_shared_memory_values(self):
        """
        Runs the callbacks of the monitored values that changed since the previous pass.
        """
        if not self._shared_memory_value_to_callback:
            return

        current_by_index: dict[int, float] = {}
        callbacks_to_trigger = []
        for name, value_index, callback in list(self._shared_memory_value_to_callback):
            if value_index not in current_by_index:
                current_by_index[value_index] = self.shared_memory.read_shared_memory_value(value_index)
            current = current_by_index[value_index]
            if current is None:
                continue
            if value_index not in self._shared_memory_value_previous or self._shared_memory_value_previous[value_index] != current:
                callbacks_to_trigger.append((name, value_index, callback))

        for name, value_index, callback in callbacks_to_trigger:
            self._log_debug(f"🚩  Shared memory value [{value_index}] changed to [{current_by_index[value_index]}]. Calling [{name}].")
            try:
                callback()
            except Exception as e:
                self._xlog.error(f"Callback [{name}] for a shared memory value failed: {e}")

        for value_index, current in current_by_index.items():
            if current is not None:
                self._shared_memory_value_previous[value_index] = current

        if callbacks_to_trigger:
            self._after_callbacks_triggered()

    def _after_callbacks_triggered(self):
        """
        Hook for subclasses: it runs after any pass of the worker that triggered at least one callback.
        The Painter one uses it to resume the painter loop, so what the callbacks changed is painted as soon as possible.
        """
        pass

    def _shared_memory_control_worker(self):
        """
        Entry point of the worker thread: runs the control loop.
        """
        try:
            self._shared_memory_control_loop()
        except (TypeError, ValueError, OSError):
            # The shared memory was closed under our feet: only expected while the monitor is being closed.
            if self.is_active:
                raise
        finally:
            # What it cost, for knowing if the doorbell is worth it: the CPU time of this thread over the passes.
            self._xlog.info(
                f"{self.__class__.__name__} finished: {self._stats['passes']} passes "
                f"({self._stats['rung']} rung, {self._stats['timeouts']} timeouts, {self._stats['polls']} polls), "
                f"{time.thread_time():.2f}s of CPU in the worker thread.")

    def _shared_memory_control_loop(self):
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
                # Every flag is read ONCE per pass. What the pass decides, and what it records as "previous" afterwards,
                #   is what it SAW. Re-reading after the callbacks would swallow a flag that flipped back meanwhile.
                registered = list(self._shared_memory_flag_to_callback)
                snapshot = {flag: self.shared_memory.read_shared_memory_flag(flag) for _, flag, _, _, _ in registered}
                # The flags with a dependant callback that has to wait: their transition must stay pending.
                waiting_flags = set()
                for name, shared_memory_flag, activation_value, callback, is_dependant in registered:

                    # Did the flag change to anything we're monitoring?
                    if self.did_shared_memory_flag_change_to_activation_value(
                            shared_memory_flag, activation_value, is_dependant, snapshot[shared_memory_flag]):

                        # Are we checking a dependant callback? If so, did the previous one already ran?
                        if is_dependant and not self.did_previous_callback_to_dependant_ran_already(name, shared_memory_flag, activation_value):
                            waiting_flags.add(shared_memory_flag)
                            self._log_debug(f"🚩  Dependant callback for shared memory flag {self.get_shared_memory_flag_name_for(shared_memory_flag)} and value {activation_value} is waiting for the previous callback to run.")
                        else:

                            # The flag changed to the value we're monitoring, so we call the callback.
                            self._log_debug(f"🚩  Shared memory flag {self.get_shared_memory_flag_name_for(shared_memory_flag)} changed to the value {activation_value}. Will call [{name}].")
                            callbacks_to_trigger.append((name, shared_memory_flag, activation_value, callback))

                # Now we trigger the callbacks that we collected.
                for name, shared_memory_flag, activation_value, callback in callbacks_to_trigger:
                    self._log_debug(f"🚩  Triggering callback [{name}] for the flag {self.get_shared_memory_flag_name_for(shared_memory_flag)} at value {activation_value}.")
                    self.trigger_callback_for_shared_memory_flag(name, shared_memory_flag, activation_value)
                
                # Finally, we record what we saw for ALL the monitored flags (not only the ones that triggered, otherwise
                #   a flag with a single activation value never learns that it went back, and its next change is missed),
                #   except the ones with a dependant callback still waiting.
                for shared_memory_flag, seen_value in snapshot.items():
                    if shared_memory_flag in waiting_flags:
                        continue
                    self._shared_memory_flag_previous_value[shared_memory_flag] = seen_value
                    if not callbacks_to_trigger:
                        continue
                    live_value = self.shared_memory.read_shared_memory_flag(shared_memory_flag)
                    if live_value != seen_value:
                        # It flipped while the callbacks ran. It is not lost: the next pass sees it as a change.
                        self._xlog.warning(
                            f"🚩  Shared memory flag {self.get_shared_memory_flag_name_for(shared_memory_flag)} changed "
                            f"from {seen_value} to {live_value} while the callbacks were running. It will be handled in the next pass.")
                
                # If we had any callback to trigger, let the subclasses react (the Painter one resumes its loop).
                if callbacks_to_trigger:
                    self._after_callbacks_triggered()

            # The values are monitored in the same pass as the flags.
            self._check_shared_memory_values()
            self._stats["passes"] += 1

            self._wait_for_next_pass()

    def _wait_for_next_pass(self):
        """
        Waits until it is time to check the shared memory again.

        With a doorbell, it sleeps until a writer rings it, which happens when a flag or a value changes,
        so nothing wakes up while nothing happens, and a change is attended at once.
        The safety timeout covers a ring that never arrives.

        Without it, it polls: if we're in idle mode, we can afford to check the shared memory less often, to reduce CPU usage,
        because we know that there won't be any interaction to paint, so we don't need to trigger the callbacks as soon as possible.
        """
        if self._doorbell is not None:
            try:
                if self._doorbell.wait(self.SAFETY_TIMEOUT_SECONDS):
                    self._stats["rung"] += 1
                else:
                    self._stats["timeouts"] += 1
                return
            except Exception as e:
                if not self.is_active:
                    return
                # Whatever it is, the monitoring has to go on: drop the doorbell and poll, like it always did.
                self._xlog.warning(f"🔔 The doorbell of {self.__class__.__name__} failed, it will poll the shared memory from now on: {type(e).__name__}: {e}")
                self._doorbell = None

        self._stats["polls"] += 1
        if self.shared_memory.read_shared_memory_flag(SHARED_DSI_LCD_IDLE_MODE):
            time.sleep(self.POLLING_IDLE_SECONDS)
        else:
            time.sleep(self.POLLING_SECONDS)

    def is_idle_mode_on(self) -> bool:
        return self.shared_memory.read_shared_memory_flag(SHARED_DSI_LCD_IDLE_MODE)