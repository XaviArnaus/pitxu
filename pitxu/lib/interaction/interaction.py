from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.utils.xprocess_pool import XprocessPool
from pitxu.lib.objects import XprocAction

from pitxu.lib.text_to_speech.piper import Piper
from pitxu.lib.text_to_speech.text_to_speech import TextToSpeech
from pitxu.lib.eink.display import Display as eInk
from pitxu.lib.matrix_led import MatrixLed
from pitxu.lib.lcd.lcd import Lcd
from pitxu.lib.dsi_lcd.dsi_lcd import DsiLcd

from sounddevice import RawInputStream
from multiprocessing import JoinableQueue

from definitions import QUEUE_SPEAKER, QUEUE_EINK, QUEUE_MATRIX, QUEUE_LCD, QUEUE_DSI_LCD,\
                        SHARED_SPEAKER_BUSY, SHARED_NETWORK_BUSY, SHARED_USER_IS_SPEAKING, \
                        SHARED_MICROPHONE_MUTED, SHARED_CHATBOT_BUSY, SHARED_CHATBOT_ANSWER_IS_ERROR, SHARED_MATRIX_BUSY,\
                        SHARED_IDLE_MODE # <-- This needs to be converted to a more overarching one.

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
    
    The idea is good, but the implementation is not yet done.
    What we have is a simpler version focused on displays in canvas/painter_busy_flags.py.
    """

    # This is what is currently being done in foreground and background
    foreground_interaction: str = None
    background_interaction: str = None

    # Subprocess control
    process_pool: XprocessPool = None

    # Be aware what to trigger in each case
    foreground_display_queue: str = None
    background_display_queue: str = None
    speech_queue: str = QUEUE_SPEAKER

    # Output queue for the speech, to allow the server to generate the audio bytes and return them through the endpoint.
    speech_output_queue: JoinableQueue = None
    speech_output_queue_sentinel: object = None

    # Map display names to their classes and queues, for initialization
    # This should probably go anyhow in the configs.
    # Also. the display name IS ASSUMED TO BE THE SAME AS THE device_config_prefix passed to the display process.
    map_display_name_to_instance_data = {
        "eink": (eInk, QUEUE_EINK),
        "matrix_led": (MatrixLed, QUEUE_MATRIX),
        "lcd": (Lcd, QUEUE_LCD),
        "dsi_lcd": (DsiLcd, QUEUE_DSI_LCD),
    }

    # Interaction delays according to the device configs, initializing with defaults
    DEFAULT_DELAY_BETWEEN_FRAMES: float = 0.05
    map_actions_to_delays: dict[str, float] = {
        XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND: 3.0,
        XprocAction.STARTUP: 3.0,
        XprocAction.THINKING: 0.05,
        XprocAction.SAY: 0.05,
    }

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Interaction, self).init_pyxavi(config=config, params=params)

        self._xlog.info("Initializing Interaction.")

        # All interactions will be done via processes
        self.process_pool = XprocessPool(config=config, params=params)

        # Load the TTS client if we're in "client" mode
        if self._xparams.get("execution_mode") == "client":
            self._xlog.info("Execution mode is 'client', initializing a generic remote TTS.")
            self.process_pool.new_and_start(self.speech_queue, target=TextToSpeech, params=Dictionary({
                "initialize_from_main": False,
            }))
        else:
            # Text to speech is the main interaction.
            # We initialize it without wanting initializations from the main Process.
            # We also grab the output queue details for the audio bytes,
            #   so we allow the server to generate the audio bytes and return them through the endpoint.
            self._xlog.debug("Initialising the Text-to-Speech with language [" + self._xparams.get("language") + "]")
            output_queue_params = self.process_pool.new_and_start(self.speech_queue, target=Piper, params=Dictionary({
                "initialize_from_main": False,
                "use_output_queue": True
            }))
            if output_queue_params is not None:
                self._log_debug("Initialized speech queue output and sentinel output queues")
                self.speech_output_queue = output_queue_params.get("output_queue", None)
                self.speech_output_queue_sentinel = output_queue_params.get("sentinel_output_queue", None)
            else:
                self._xlog.warning("🟠 No output queue params returned from initializing the speech queue. Output queue for audio bytes will not be available.")

        # Initialize the required displays
        self._initialize_displays()
    
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
        
        # Initialize each display
        for display_name in displays_to_use:

            # Initialize the parameters that we'll inject into the display process
            params = Dictionary({"device_config_prefix": display_name})

            # Load interaction delays from the device configs
            if self._xconfig.key_exists(f"{display_name}.delays"):
                # Foreground display
                if display_name == foreground_display:
                    if self._xconfig.key_exists(f"{display_name}.delays.foreground_notifications"):
                        self.map_actions_to_delays[XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND] = self._xconfig.get(f"{display_name}.delays.foreground_notifications")
                    if self._xconfig.key_exists(f"{display_name}.delays.startup_splash"):
                        self.map_actions_to_delays[XprocAction.STARTUP] = self._xconfig.get(f"{display_name}.delays.startup_splash")
                # Background display
                if display_name == background_display:
                    if self._xconfig.key_exists(f"{display_name}.delays.default_delay_between_frames"):
                        self.DEFAULT_DELAY_BETWEEN_FRAMES = self._xconfig.get(f"{display_name}.delays.default_delay_between_frames")
                    if self._xconfig.key_exists(f"{display_name}.delays.thinking"):
                        self.map_actions_to_delays[XprocAction.THINKING] = self._xconfig.get(f"{display_name}.delays.thinking", self.DEFAULT_DELAY_BETWEEN_FRAMES)
                    if self._xconfig.key_exists(f"{display_name}.delays.speaking"):
                        self.map_actions_to_delays[XprocAction.SAY] = self._xconfig.get(f"{display_name}.delays.speaking", self.DEFAULT_DELAY_BETWEEN_FRAMES)
                
                # Add these parameters to the display process params
                params.set("interaction_delays", {
                    "default_delay_between_frames": self.DEFAULT_DELAY_BETWEEN_FRAMES,
                    "foreground_notifications": self.map_actions_to_delays.get(XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND),
                    "startup_splash": self.map_actions_to_delays.get(XprocAction.STARTUP),
                    "thinking": self.map_actions_to_delays.get(XprocAction.THINKING),
                    "speaking": self.map_actions_to_delays.get(XprocAction.SAY),
                })
            

            # Initialize the displays via the process pool
            display_class, display_queue = self.map_display_name_to_instance_data.get(display_name, (None, None))
            if display_class is not None:
                self._xlog.info(f"Initialising [{display_name}] with queue [{display_queue}] for Display Interaction.")
                self.process_pool.new_and_start(display_queue, target=display_class, params=params)
            else:
                self._xlog.error(f"Display class for {display_name} not found. Cannot initialize it. Stopping.")
                raise RuntimeError(f"Display class for {display_name} not found.")
    
    def displays_are_combined(self) -> bool:
        """
        Check if the foreground and background displays are the same.

        Returns:
            bool: True if both displays are the same, False otherwise.
        """
        return self.foreground_display_queue == self.background_display_queue
    
    def get_delay_for_action(self, action: XprocAction) -> float:
        return self.map_actions_to_delays.get(action)
    
    def get_delay_between_frames(self) -> float:
        return self.DEFAULT_DELAY_BETWEEN_FRAMES
    
    def close(self):
        """
        Close the Interaction, including the BusyFlagsManager.
        """
        self._xlog.debug("Closing Interaction.")

        self.process_pool.get_memory_manager().force_all_flags_to_idle()
    
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

        # If we're in client mode, this is going to the server, so it may take time.
        # Show the thinking effect while grabbing the TTS response from the server.
        if self._xconfig.get("app.execution_mode") == "client":
            self._log_debug(f"🗣️ Execution mode is 'client', the speech flow is different")

            # Gathering the TTS response from the server may take time.
            # We do it in a split step, so we can show the thinking animation while waiting for the server 
            # to respond with the TTS audio bytes.
            self.show_networking()

            self._log_debug(f"🗣️ Gatehring TTS from the server")
            self.process_pool.send(QUEUE_SPEAKER, XprocAction.GATHER_TTS, message)

            self.wait_for_server_to_start_and_finish_networking()

            # Now the TTS class has the audio bytes, now we do the "normal" flow.

            # The background display depends on the configuration.
            self._log_debug(f"🗣️ Sending SAY command to Background display")
            self.process_pool.send(self._get_active_background_display_queue(), XprocAction.SAY, message)

            # Speech is a direct process command.
            self._log_debug(f"🗣️ Sending PLAY_TTS command to Speaker")
            self.process_pool.send(QUEUE_SPEAKER, XprocAction.PLAY_TTS)

            # We want that the main thread waits until the actions finished in the subprocesses
            self._log_debug(f"🗣️ Waiting for Speaker and Display to start and finish speaking")
            self.wait_for_speaker_to_start_and_finish_speaking()
            self.wait_for_busy_background_display_to_idle()

        else:

            # The background display depends on the configuration.
            self._log_debug(f"🗣️ Sending SAY command to Background display")
            self.process_pool.send(self._get_active_background_display_queue(), XprocAction.SAY, message)

            # Speech is a direct process command.
            self._log_debug(f"🗣️ Sending SAY command to Speaker")
            self.process_pool.send(QUEUE_SPEAKER, XprocAction.SAY, message)

            # We want that the main thread waits until the actions finished in the subprocesses
            self._log_debug(f"🗣️ Waiting for Speaker and Display to start and finish speaking")
            self.wait_for_speaker_to_start_and_finish_speaking()
            self.wait_for_busy_background_display_to_idle()
            # COMMENTED: This should not be needed. Display is not busy, no elements waiting FOR THIS INTERACTION.
            # self.wait_for_background_display_queue_to_empty()
    
    def generate_speech_audio_bytes(self, message: str) -> dict:
        """
        Generates the audio bytes for a given message via Text-To-Speech, and returns them.

        This is useful for example for the server endpoint, to generate the audio bytes and return them through the endpoint.

        Args:
            message (str): The message to generate the audio bytes for.
        Returns:
            dict: A dictionary containing the generated audio bytes and the sample rate.
        """

        from numpy import ndarray

        self._xlog.debug(f"*️⃣ Generating speech audio bytes for message: {message}")

        # Speech is a direct process command.
        self._log_debug(f"*️⃣ Sending SAY_OUTPUT_QUEUE command to Speaker with output queue")
        self.process_pool.send(QUEUE_SPEAKER, XprocAction.SAY_OUTPUT_QUEUE, message)

        # We wait for the output queue to be filled with the audio bytes, and then we return them.
        self._log_debug(f"*️⃣ Waiting for audio bytes to be generated and returned through the output queue")
        self.wait_for_busy_speech_to_idle()
        self.wait_for_speech_queue_to_empty()

        self._log_debug(f"*️⃣ Retrieving audio bytes from the output queue")
        audio_bytes = []
        sample_rate = 0
        while True:
            audio_chunk_data = self.speech_output_queue.get()
            # Apparently we can't simply compare the item with the sentinel value.
            # The value in item is an array of bytes, so we better check types first.
            if isinstance(audio_chunk_data, dict) and \
                    audio_chunk_data.get("audio_bytes") is not None and \
                    audio_chunk_data.get("sample_rate") is not None and \
                    isinstance(audio_chunk_data.get("audio_bytes"), ndarray):
                
                self._log_debug(f"*️⃣ Got a chunk of audio bytes: {len(audio_chunk_data.get('audio_bytes'))} bytes at sample rate {audio_chunk_data.get('sample_rate')}")
                audio_bytes.append(audio_chunk_data.get("audio_bytes"))
                sample_rate = audio_chunk_data.get("sample_rate")

            elif audio_chunk_data is self.speech_output_queue_sentinel:
                self._log_debug(f"*️⃣ Received sentinel value from output queue, finished receiving audio bytes")
                break

            else:
                self._log_debug(f"*️⃣ Received unknown item from output queue: {audio_chunk_data}, ignoring it")
                if self.speech_output_queue.empty():
                    self._log_debug(f"*️⃣ Output queue is empty after receiving unknown item, breaking the loop")
                    break

        self._log_debug(f"*️⃣ Audio bytes generation completed, returning the bytes")

        return {
            "audio_bytes": b"".join(audio_bytes),
            "sample_rate": sample_rate
        }
    
    def show_thinking(self):
        """
        Triggers a "thinking" interaction on the background display.

        This needs the SHARED_CHATBOT_BUSY flag to be set by the Chatbot/Main process.
        TODO: this is a clear candidate to the BusyFlagsManager automatic handling.
        """

        self._xlog.debug("🤖 Triggering thinking interaction on background display.")

        self.process_pool.send(self._get_active_background_display_queue(), XprocAction.THINKING)
    
    def show_networking(self):
        """
        Triggers a "networking" interaction on the background display.

        This needs the SHARED_NETWORK_BUSY flag to be set by the Communication/Main process.
        TODO: this is a clear candidate to the BusyFlagsManager automatic handling.
        """

        self._xlog.debug("🤖 Triggering networking interaction on background display.")

        self.process_pool.send(self._get_active_background_display_queue(), XprocAction.NETWORKING)
    
    def startup_splash(self, for_seconds: float = 3.0):
        """
        Show the startup splash screen on the Foreground display.
        """
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.STARTUP, str(for_seconds))
    
    def show_error(self, text: str, for_seconds: float = 3.0):
        """
        Show the error screen on the Foreground display.
        """
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.SHOW_ERROR, {
            "text": text,
            "for_seconds": for_seconds
        })

    def show_init_phases(self, step: int, text: str = None):
        """
        Show the initialization phases on the Background display.
        """
        self.process_pool.send(self._get_active_background_display_queue(), XprocAction.INIT_STEP, (str(step), text))

    def show_idle(self):
        """
        Show the idle mode on the Foreground display.
        """
        self._xlog.debug("👀 Starting idle mode from Interaction class")
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_IDLE_MODE, True)
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.SHOW_IDLE)
    
    def show_arbitrary_text_on_foreground(
            self,
            icon: str = None,
            text: str = None,
            font_size: int = 24,
            header: str = None,
            font_header_size: int = 32,
            padding = 5,
            show_for_seconds = None
        ):
        """
        Shows arbitrary text on the foreground display.
        """
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND, {
            "icon": icon,
            "text": text,
            "font_size": font_size,
            "header": header,
            "font_header_size": font_header_size,
            "padding": padding,
            "show_for_seconds": show_for_seconds
        })
    
    def show_arbitrary_text_on_foreground_while_idle(
            self,
            icon: str = None,
            text: str = None,
            font_size: int = 24,
            header: str = None,
            font_header_size: int = 32,
            padding = 5,
            show_for_seconds = None
        ):
        """
        Shows arbitrary text on the foreground display.
        """
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND_IDLE, {
            "icon": icon,
            "text": text,
            "font_size": font_size,
            "header": header,
            "font_header_size": font_header_size,
            "padding": padding,
            "show_for_seconds": show_for_seconds
        })
    
    def show_arbitrary_icon_on_foreground(
            self,
            icon: str = None,
            text: str = None,
            color: str = None
        ):
        """
        Shows arbitrary icon on the foreground display.
        """
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.SHOW_ARBITRARY_ICON_FOREGROUND, {
            "icon": icon,
            "text": text,
            "color": color
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
        Shows arbitrary text on the foreground display only while speaking.
        """
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND_SPEAKING, {
            "icon": icon,
            "text": text,
            "font_size": font_size,
            "header": header,
            "font_header_size": font_header_size,
            "padding": padding
        })
    
    def show_arbitrary_text_on_foreground_while_thinking(
            self,
            icon: str = None,
            text: str = None,
            font_size: int = 24,
            header: str = None,
            font_header_size: int = 32,
            padding = 5
        ):
        """
        Shows arbitrary text on the foreground display only while thinking.
        """
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND_THINKING, {
            "icon": icon,
            "text": text,
            "font_size": font_size,
            "header": header,
            "font_header_size": font_header_size,
            "padding": padding
        })
    
    def show_arbitrary_text_on_foreground_while_networking(
            self,
            icon: str = None,
            text: str = None,
            font_size: int = 24,
            header: str = None,
            font_header_size: int = 32,
            padding = 5
        ):
        """
        Shows arbitrary text on the foreground display only while networking.
        """
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND_NETWORKING, {
            "icon": icon,
            "text": text,
            "font_size": font_size,
            "header": header,
            "font_header_size": font_header_size,
            "padding": padding
        })
    
    def show_code_block_on_foreground(self, code: str, for_seconds: float = 10.0):
        """
        Shows a code block on the foreground display.

        Args:
            code (str): The code block to show.
        """
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.SHOW_CODE_BLOCK, {
            "code": code,
            "for_seconds": for_seconds
        })
    
    def show_interaction_holding_percentage(self, percentage: int):
        """
        Shows the interaction holding percentage on the background display.

        Args:
            percentage (int): The percentage of time left for the interaction.
        """
        self._log_debug(f"🚥 Showing interaction holding percentage {percentage}% on background display")
        self.process_pool.send(self._get_active_background_display_queue(), XprocAction.INTERACTION_HOLDING_PERCENTAGE, percentage)

    # --------- (Proxy) Functions to clear screens ---------

    def clear_foreground_display(self):
        # Only for eInk: Hard Clear is slow. As we can use partial refresh, we do a soft clear first.
        if self._get_active_foreground_display_queue() == QUEUE_EINK:
            # First a soft clear, so the screen is white
            self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.SOFT_CLEAR)

        # Full clear, to ensure a reset.
        # self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.CLEAR)
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.FOREGROUND_CLEAR)

    def clear_background_display(self):
        self.process_pool.send(self._get_active_background_display_queue(), XprocAction.BACKGROUND_CLEAR)
    
    def clear_combined_display(self):
        # They are combined, so let's send the clear to just one of it. Picking randomly Background.
        self.clear_background_display()
    
    # --------- (Proxy) Functions to wait for queues to be empty and busy flags to idle ---------

    def wait_for_speaker_to_start_and_finish_speaking(self):
        self.process_pool.get_memory_manager().wait_for_busy_process_to_be_busy(SHARED_SPEAKER_BUSY)
        self.process_pool.get_memory_manager().wait_for_busy_process_to_idle(SHARED_SPEAKER_BUSY)
    
    def wait_for_server_to_start_and_finish_thinking(self):
        self.process_pool.get_memory_manager().wait_for_busy_process_to_be_busy(SHARED_CHATBOT_BUSY)
        self.process_pool.get_memory_manager().wait_for_busy_process_to_idle(SHARED_CHATBOT_BUSY)
    
    def wait_for_server_to_start_and_finish_networking(self):
        self.process_pool.get_memory_manager().wait_for_busy_process_to_be_busy(SHARED_NETWORK_BUSY)
        self.process_pool.get_memory_manager().wait_for_busy_process_to_idle(SHARED_NETWORK_BUSY)
    
    def wait_for_speaker_to_finish_speaking(self):
        self.process_pool.get_memory_manager().wait_for_busy_process_to_idle(SHARED_SPEAKER_BUSY)

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
    
    def wait_for_microphone_to_be_unmuted(self):
        self.process_pool.get_memory_manager().wait_for_busy_process_to_idle(SHARED_MICROPHONE_MUTED)
    
    def wait_for_microphone_to_be_muted(self):
        self.process_pool.get_memory_manager().wait_for_busy_process_to_be_busy(SHARED_MICROPHONE_MUTED)
    
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

    def mute_microphone(self, input_stream: RawInputStream = None):
        if input_stream:
            self._log_debug("🔇 Stopping the input stream as microphone is muting.")
            input_stream.stop()
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_MICROPHONE_MUTED, True)
        self._log_debug("🔇 Muting the microphone. Now mute is [" + str(self.process_pool.get_memory_manager().read_shared_memory_flag(SHARED_MICROPHONE_MUTED)) + "]")

    def unmute_microphone(self, input_stream: RawInputStream = None):
        if input_stream:
            self._log_debug("🔊 Starting the input stream as microphone is unmuting.")
            input_stream.start()
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
    
    def set_communication_busy(self):
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_NETWORK_BUSY, True)
        self._log_debug("🤖 Setting Communication as busy.")
    
    def unset_communication_busy(self):
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_NETWORK_BUSY, False)
        self._log_debug("🤖 Unsetting Communication as busy.")
    
    def is_communication_busy(self) -> bool:
        return self.process_pool.get_memory_manager().read_shared_memory_flag(SHARED_NETWORK_BUSY)

    def is_chatbot_error(self) -> bool:
        return self.process_pool.get_memory_manager().read_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR)

    def unset_chatbot_error(self):
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, False)
    
    def is_idle_mode_on(self) -> bool:
        return self.process_pool.get_memory_manager().read_shared_memory_flag(SHARED_IDLE_MODE)

    def set_idle_mode_on(self):
        self._log_debug("💤  Setting idle mode on.")
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_IDLE_MODE, True)

    def set_idle_mode_off(self):
        self._log_debug("💤  Setting idle mode off.")
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_IDLE_MODE, False)

    def is_matrix_busy(self):
        return self.process_pool.get_memory_manager().read_shared_memory_flag(SHARED_MATRIX_BUSY)

    def is_background_display_busy(self):
        return self.process_pool.get_memory_manager().read_shared_memory_flag(self._get_active_background_display_busy_flag())
    
    def set_speaker_busy(self):
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_SPEAKER_BUSY, True)
    
    def unset_speaker_busy(self):
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_SPEAKER_BUSY, False)
    
    def set_user_is_speaking(self):
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_USER_IS_SPEAKING, True)
    
    def unset_user_is_speaking(self):
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_USER_IS_SPEAKING, False)

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
        
