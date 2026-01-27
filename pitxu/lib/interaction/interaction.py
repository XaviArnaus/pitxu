from pyxavi import Config, Dictionary, full_stack
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.interaction.CommConstants import BackgroundComm, ForegroundComm
from pitxu.lib.interaction.busy_flags_manager import BusyFlagsManager
from pitxu.lib.utils.xprocess_pool import XprocessPool
from pitxu.lib.objects import XprocAction

from pitxu.lib.text_to_speech import Piper
from pitxu.lib.eink.display import Display as eInk
from pitxu.lib.matrix_led import MatrixLed
from pitxu.lib.lcd.lcd import Lcd

from definitions import QUEUE_SPEAKER, QUEUE_EINK, QUEUE_MATRIX, QUEUE_LCD,\
                        SHARED_SPEAKER_BUSY,\
                        SHARED_MICROPHONE_MUTED, SHARED_CHATBOT_BUSY, SHARED_CHATBOT_ANSWER_IS_ERROR, SHARED_MATRIX_BUSY,\
                        SHARED_EINK_IDLE_MODE # <-- This needs to be converted to a more overarching one.

import time

class Interaction(PyXavi):
    """
    Class to manage the interaction states of the system, including
    foreground and background interactions, and busy flags.

    The concept is the following:

    - Main decides to perform an interaction (foreground interaction)
        - This can be, for example, showing a message on the display, or speaking a text.
        - Therefore, Main calls Interaction.communicate() so it gets executed.
        - While this happen, busy state changes may happen, for example, the speaker
          becomes busy because it is speaking the text.
        - Interaction listens to busy flags changes via BusyFlagsManager, and sees if any extra interaction
          needs to be performed (background interaction).
        - If so, Interaction triggers the background interaction (for example, showing the "speaking" icon on the display).
        - If the background interaction is no longer needed, Interaction stops it, by listening to the busy flags changes.
    """

    # Busy flag changes manager
    busy_flags_manager: BusyFlagsManager = None

    # This is what is currently being done in foreground and background
    foreground_interaction: str = None
    background_interaction: str = None

    # Subprocess control
    process_pool: XprocessPool = None

    # Be aware what to trigger in each case
    foreground_display_queue: str = None
    background_display_queue: str = None
    speech_queue: str = QUEUE_SPEAKER

    # Map display names to their classes and queues, for initialization
    # This should probably go anyhow in the configs.
    # Also. the display name IS ASSUMED TO BE THE SAME AS THE device_config_prefix passed to the display process.
    map_display_name_to_instance_data = {
        "eink": (eInk, QUEUE_EINK),
        "matrix_led": (MatrixLed, QUEUE_MATRIX),
        "lcd": (Lcd, QUEUE_LCD)
    }

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Interaction, self).init_pyxavi(config=config, params=params)

        self._xlog.info("Initializing Interaction.")

        # All interactions will be done via processes
        self.process_pool = XprocessPool(config=config, params=params)

        # Define which is going to be the callback for busy flags changes
        # and initialize the BusyFlagsManager. Works via threading.
        # COMMENTED OUT FOR NOW, we don't need it yet and causes probles when pickling the _thread.lock
        #   TypeError: cannot pickle '_thread.lock' objec
        # params.set("busy_flags_callback", self.busy_flags_callback)
        # self.busy_flags_manager = BusyFlagsManager(config=config, params=params)

        # Text to speech is the main interaction. We initialize it without wanting initializations from the main Process.
        self._xlog.debug("Initialising the Text-to-Speech with language [" + self._xparams.get("language") + "]")
        self.process_pool.new_and_start(self.speech_queue, target=Piper, params=Dictionary({"initialize_from_main": False}))

        # Initialize the required displays
        self._initialize_displays()

        # Start listening to busy flag changes
        if self.busy_flags_manager is not None:
            self._xlog.debug("Starting BusyFlagsManager listening to flag changes.")
            self.busy_flags_manager.start_listening_flag_changes()
    
    def _initialize_displays(self):
        """
        Initialize the displays used for interaction.

        This depends on what is defined in the configs.
        """

        # Calculate which display to initialize
        available_displays = self._xconfig.get("displays.available_displays", [])
        displays_to_use = []
        foreground_display = self._xconfig.get("displays.foreground_display", None)
        background_display = self._xconfig.get("displays.background_display", None)
        # Now that we're here, just remember which queues to use for foreground and background
        self.foreground_display_queue = self.map_display_name_to_instance_data.get(foreground_display, (None, None))[1]
        self.background_display_queue = self.map_display_name_to_instance_data.get(background_display, (None, None))[1]
        # Add them to the list of displays to use
        if foreground_display is not None\
            and foreground_display in available_displays\
            and foreground_display not in displays_to_use:
            displays_to_use.append(foreground_display)
        if background_display is not None\
            and background_display in available_displays\
            and background_display not in displays_to_use:
            displays_to_use.append(background_display)
        
        # Initialize the displays via the process pool
        for display_name in displays_to_use:
            display_class, display_queue = self.map_display_name_to_instance_data.get(display_name, (None, None))
            if display_class is not None:
                self._xlog.info(f"Initialising [{display_name}] with queue [{display_queue}] for Display Interaction.")
                params = Dictionary({"device_config_prefix": display_name})
                self.process_pool.new_and_start(display_queue, target=display_class, params=params)
            else:
                self._xlog.error(f"Display class for {display_name} not found. Cannot initialize it. Stopping.")
                raise RuntimeError(f"Display class for {display_name} not found.")
    
    def close(self):
        """
        Close the Interaction, including the BusyFlagsManager.
        """
        self._xlog.debug("Closing Interaction.")
        if self.busy_flags_manager is not None:
            self.busy_flags_manager.close()
            self.busy_flags_manager = None
    
    # --------- (Proxy) Functions to trigger interactions ---------
    
    def say(self, message: str):
        """
        Triggers a speech interaction via Text-To-Speech, with any side effect like
        showing the "speaking" icon on the background display.

        Keep in mind that nothing actually should continue until the speech is done.

        Args:
            message (str): The message to speak.
        """

        self._xlog.debug(f"🗣️ Triggering speech interaction: {message}")

        # We need to start from a clean state, at least from the background display point of view.
        self.clear_background_display()

        # As long as we can't stop inmediately the animations on the Background Display,
        # we need to wait until it's idle before starting a new speech interaction.
        # TODO: Seems like it is waiting forever to THINKING state to end. Why? Most likelky we never unset it. Checking.
        self.process_pool._shared_memory.wait_for_busy_process_to_idle(self._get_active_background_display_busy_flag())

        # Speech is a direct process command.
        self.process_pool.send(QUEUE_SPEAKER, XprocAction.SAY, message)

        # The background display depends on the configuration.
        self.process_pool.send(self._get_active_background_display_queue(), XprocAction.SAY, message)

        # We want that the main thread waits until the actions finished in the subprocesses
        self.process_pool.wait_for_queue_to_empty(QUEUE_SPEAKER)
        self.process_pool._shared_memory.wait_for_busy_process_to_idle(SHARED_SPEAKER_BUSY)
        self.process_pool.wait_for_queue_to_empty(self._get_active_background_display_queue())
        self.process_pool._shared_memory.wait_for_busy_process_to_idle(self._get_active_background_display_busy_flag())
    
    def show_thinking(self):
        """
        Triggers a "thinking" interaction on the background display.

        This needs the SHARED_CHATBOT_BUSY flag to be set by the Chatbot/Main process.
        TODO: this is a clear candidate to the BusyFlagsManager automatic handling.
        """

        self._xlog.debug("🤖 Triggering thinking interaction on background display.")

        self.process_pool.send(self._get_active_background_display_queue(), XprocAction.THINKING)
    
    # def show(self, message: str):
    #     self._process_pool.send(QUEUE_EINK, XprocAction.SHOW, message)
    
    def startup_splash(self, for_seconds: float = 3.0):
        """
        Show the startup splash screen on the Foreground display.
        """
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.STARTUP, str(for_seconds))

    def show_init_phases(self, step: int):
        """
        Show the initialization phases on the Background display.
        """
        self.process_pool.send(self._get_active_background_display_queue(), XprocAction.INIT_STEP, str(step))

    def show_idle(self):
        """
        Show the idle mode on the Foreground display.
        """
        self._xlog.debug("👀 Starting idle mode from Interaction class")
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_EINK_IDLE_MODE, True)
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.SHOW_IDLE)
    
    def show_arbitrary_text_on_foreground(
            self,
            icon: str = None,
            text: str = None,
            font_size: int = 24,
            header: str = None,
            font_header_size: int = 32,
            padding = 5
        ):
        """
        Shows arbitrary text on the eInk display.

        TODO: This should be generalized to other displays.
        """
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND, {
            "icon": icon,
            "text": text,
            "font_size": font_size,
            "header": header,
            "font_header_size": font_header_size,
            "padding": padding
        })

    def show_arbitrary_text_on_foreground_while_speaking(
            self,
            icon: str = None,
            text: str = None,
            font_size: int = 24,
            header: str = None,
            font_header_size: int = 32,
            padding = 5
        ):
        """
        Shows arbitrary text on the eInk display only while speaking.
        """
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND_TALKING, {
            "icon": icon,
            "text": text,
            "font_size": font_size,
            "header": header,
            "font_header_size": font_header_size,
            "padding": padding
        })
    
    def show_interaction_holding_percentage(self, percentage: int):
        """
        Shows the interaction holding percentage on the background display.

        Args:
            percentage (int): The percentage of time left for the interaction.
        """
        self._xlog.info(f"🚥 Showing interaction holding percentage {percentage}% on background display")
        self.process_pool.send(self._get_active_background_display_queue(), XprocAction.INTERACTION_HOLDING_PERCENTAGE, percentage)

    # --------- (Proxy) Functions to clear screens ---------

    def clear_foreground_display(self):
        # Only for eInk: Hard Clear is slow. As we can use partial refresh, we do a soft clear first.
        if self._get_active_foreground_display_queue() == QUEUE_EINK:
            # First a soft clear, so the screen is white
            self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.SOFT_CLEAR)

        # Full clear, to ensure a reset.
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.CLEAR)

    def clear_background_display(self):
        # TODO: This should be unified into a XprocAction.SOFT_CLEAR / XprocAction.CLEAR
        # self.process_pool.send(self._get_active_background_display_queue(), XprocAction.LED_CLEAR)
        self.process_pool.send(self._get_active_background_display_queue(), XprocAction.BACKGROUND_CLEAR)
    
    # --------- (Proxy) Functions to wait for queues to be empty and busy flags to idle ---------

    def wait_for_foreground_display_queue_to_empty(self):
        self.process_pool.wait_for_queue_to_empty(self._get_active_foreground_display_queue())
    
    def wait_for_background_display_queue_to_empty(self):
        self.process_pool.wait_for_queue_to_empty(self._get_active_background_display_queue())
    
    def wait_for_speech_queue_to_empty(self):
        self.process_pool.wait_for_queue_to_empty(self.speech_queue)
    
    def wait_for_all_queues_to_empty(self):
        self.process_pool.wait_for_all_queues_to_empty()
    
    def wait_for_busy_foreground_display_to_idle(self):
        self.process_pool.get_memory_manager().wait_for_busy_process_to_idle(self._get_active_foreground_display_busy_flag())
    
    def wait_for_busy_background_display_to_idle(self):
        self.process_pool.get_memory_manager().wait_for_busy_process_to_idle(self._get_active_background_display_busy_flag())
    
    def wait_for_busy_speech_to_idle(self):
        self.process_pool.get_memory_manager().wait_for_busy_process_to_idle(SHARED_SPEAKER_BUSY)
    
    def wait_for_all_busy_processes_to_idle(self):
        self.process_pool.get_memory_manager().wait_for_all_busy_process_to_idle()
    
    # --------- Functions to retrieve data from the processes ---------

    def get_process_pool(self) -> XprocessPool:
        return self.process_pool
    
    def get_canvas_from_foreground_display(self):
        return self.process_pool.get_process(self._get_active_foreground_display_queue()).get_canvas_handler()
    
    def get_canvas_from_background_display(self):
        return self.process_pool.get_process(self._get_active_background_display_queue()).get_canvas_handler()
    
    # --------- Proxy functions for Shared Memory Management ---------

    def mute_microphone(self):
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_MICROPHONE_MUTED, True)
        self._log_debug("🔇 Muting the microphone. Now mute is [" + str(self.process_pool.get_memory_manager().read_shared_memory_flag(SHARED_MICROPHONE_MUTED)) + "]")

    def unmute_microphone(self):
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_MICROPHONE_MUTED, False)
        self._log_debug("🔊 Unmuting the microphone. Now mute is [" + str(self.process_pool.get_memory_manager().read_shared_memory_flag(SHARED_MICROPHONE_MUTED)) + "]")
    
    def is_microphone_muted(self) -> bool:
        return self.process_pool.get_memory_manager().read_shared_memory_flag(SHARED_MICROPHONE_MUTED)

    def set_chatbot_busy(self):
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_CHATBOT_BUSY, True)
        self._log_debug("🤖 Setting Chatbot as busy.")
    
    def unset_chatbot_busy(self):
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_CHATBOT_BUSY, False)
        self._log_debug("🤖 Unsetting Chatbot as busy.")
    
    def is_chatbot_busy(self) -> bool:
        return self.process_pool.get_memory_manager().read_shared_memory_flag(SHARED_CHATBOT_BUSY)

    def is_chatbot_error(self) -> bool:
        return self.process_pool.get_memory_manager().read_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR)

    def unset_chatbot_error(self):
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, False)
    
    def is_eink_in_idle_mode(self) -> bool:
        return self.process_pool.get_memory_manager().read_shared_memory_flag(SHARED_EINK_IDLE_MODE)

    def set_eink_idle_mode(self):
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_EINK_IDLE_MODE, True)

    def unset_eink_idle_mode(self):
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_EINK_IDLE_MODE, False)

    def is_matrix_busy(self):
        return self.process_pool.get_memory_manager().read_shared_memory_flag(SHARED_MATRIX_BUSY)

    def is_background_display_busy(self):
        return self.process_pool.get_memory_manager().read_shared_memory_flag(self._get_active_background_display_busy_flag())

    # --------- Internal helper functions ---------

    def _get_active_background_display_queue(self):
        """
        Get the active background display queue.

        Returns:
            str: The queue name of the active background display.
        """
        return self.background_display_queue
    
    def _get_active_background_display_busy_flag(self):
        """
        Get the active background display busy flag.

        Returns:
            str: The busy flag name of the active background display.
        """
        return self.process_pool.get_busy_flag_from_related_queue(self._get_active_background_display_queue())
    
    def _get_active_foreground_display_queue(self):
        """
        Get the active foreground display queue.

        Returns:
            str: The queue name of the active foreground display.
        """
        return self.foreground_display_queue

    def _get_active_foreground_display_busy_flag(self):
        """
        Get the active foreground display busy flag.

        Returns:
            str: The busy flag name of the active foreground display.
        """
        return self.process_pool.get_busy_flag_from_related_queue(self._get_active_foreground_display_queue())
    
    # --------- I'm not sure if we actually need this at all ---------
    
    def busy_flags_callback(self, state_name: str, new_value: bool):
        """
        Callback called when a busy flag changes state.

        Args:
            state_name (str): The name of the state that changed.
            new_value (bool): The new value of the state.
        """
        self._xlog.debug(f"Interaction received busy flag change: {state_name} = {new_value}")

        # Identify what was changed and update the interaction state accordingly
        if state_name == BusyFlagsManager.STATE_SPEAKER:
            if new_value:
                self.background_interaction = BackgroundComm.SPEAKING
            else:
                self.background_interaction = None
        elif state_name == BusyFlagsManager.STATE_CHATBOT:
            if new_value:
                self.background_interaction = BackgroundComm.THINKING
            else:
                self.background_interaction = None
        
        # Now clear the communication and re-trigger it.
    
    def trigger_visual_communication(self):
        # To be implemented in subclasses
        pass
        
