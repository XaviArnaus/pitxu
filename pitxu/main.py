from subprocess import call

from pyxavi import Config, Dictionary, Storage, full_stack, dd

import signal
from functools import partial

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.text import Text
from pitxu.lib.utils.stopwatch import Stopwatch
from pitxu.lib.utils.memory import Memory
from pitxu.lib.utils.maintenance import Maintenance
from pitxu.lib.utils.reminders import Reminders
from pitxu.lib.utils.fan_control import FanControl
from pitxu.lib.chatbot import GeminiChatbot
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.canvas.canvas import Canvas
from pitxu.lib.speech_to_text.vosk import Vosk, VoskException
from pitxu.lib.speech_to_text.capture_handler import CaptureHandler
from pitxu.lib.objects import ChatbotResponse, FunctionCallPair
from pitxu.lib.microservice.server import Server

import sys
import sounddevice
import time
from copy import deepcopy
from datetime import datetime

class Main(PyXavi):

    _state: Storage = None
    
    _last_processed_minute: int = -1
    _last_processed_second: int = -1
    _last_processed_interaction_percentage: int = -1
    _last_interaction_datetime: datetime = None
    _seconds_to_hold_interaction_answer: int = 15

    _server: Server = None
    _fan_control_iterated_seconds: int = -1
    _fan_control_trigger_every_seconds: int = 5

    _chatbot: GeminiChatbot = None
    _dictate: Vosk = None
    _raw_input_stream: sounddevice.RawInputStream = None
    _capture_handler: CaptureHandler = None

    _is_pitxu_active: bool = True

    _chatbot_client_callbacks: dict[str, callable] = None

    _maintenance: Maintenance = None
    _reminders: Reminders = None
    _fan_control: FanControl = None

    _stopwatch: Stopwatch = None
    _supported_languages: list = []
    _greeting_sentence: str = None
    _goodbye_sentence: str = None
    _trigger_answers: list[str] = []
    _exit_words: list = []
    _trigger_words: list = []
    _tokens_counter: int = 0

    ENGLISH: str = "en-us"
    CATALAN: str = "ca"
    GERMAN: str = "de"
    SPANISH: str = "es"

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):

        super(Main, self).init_pyxavi(config=config, params=params)

        # Handle SIGTERM for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # Initialize State
        self._state = Storage(filename=self._xconfig.get("storage.path") + self._xconfig.get("storage.state_file"))

        # Initial Language. 1st from the state, then from the config, and last default to Catalan.
        language = self._state.get("language", config.get("app.default_language", self.CATALAN))
        self._xparams.set("language", language)

        # Initialize Maintenance utility
        self._maintenance = Maintenance(config=self._xconfig, params=self._xparams)

        # Supported Languages
        self._supported_languages = config.get("app.supported_languages")

        # Check and complain if the initial language is not supported
        if self._xparams.get("language") not in self._supported_languages:
            self._xlog.error(f"🛑 Initial language [{self._xparams.get('language')}] is not in the supported languages list: {self._supported_languages}")
            self._xlog.error("🛑 Please change the initial language in the state file or the default language in the config file to one of the supported languages.")
            self._xlog.error("🛑 Supported languages are: " + ", ".join(self._supported_languages))
            self._xlog.error("🛑 Exiting now.")
            sys.exit(1)

        # The Reminders functionality
        self._reminders = Reminders(config=self._xconfig, params=self._xparams)

        # Stopwatch to measure times
        self._stopwatch = Stopwatch()
    
    def _handle_signal(self, sig, frame):
        """
        Handle signals for graceful shutdown.
        This is set to handle SIGTERM, that is the signal sent by systemctl stop and reboot commands.

        This allows the service to stop gracefully when receiving a termination signal,
        that happens with systemctl stop or reboot commands.
        """

        signal_name = signal.Signals(sig).name if sig in signal.Signals.__members__.values() else str(sig)

        self._xlog.warning(f"🔪 Signal [{signal_name}] received in Main, closing nicely now...")
        self.close_nicely()
    
    def _load_models(self):
        
        # Initialise Speech-to-Text. This runs in the main process
        self._xlog.debug("Initialising the Speech-to-Text with language [" + self._xparams.get("language") + "]")
        # COMMENTED: This way Vosk chooses between config or device.
        # self._xparams.set("samplerate", self._xconfig.get("speech-to-text.input_samplerate"))
        self._dictate = Vosk(config=self._xconfig, params=self._xparams)
        input_audio_chunk_queue = self._dictate.get_queue()

        # Initialise the Capture Handler, that captures the audio from the microphone.
        # It needs the original samplerate so that it can resample the chunk from it to 16 kHz.
        samplerate = self.get_samplerate()
        self._capture_handler = CaptureHandler(config=self._xconfig, params=Dictionary({
            "capture_queue": input_audio_chunk_queue,
            "microphone_samplerate": samplerate,
            "target_samplerate": self._xconfig.get("speech-to-text.target_samplerate", 16000)
        }))

        # # Initialise the Raw Input Stream for microphone
        # self._xlog.debug("Initialising the Raw Input Stream for microphone")
        # if self._xconfig.get("speech_to_text.mock", True) is False:
        #     self._xlog.info("Loading Real Raw Input Stream (mic) for Speech-to-Text by Config")
        #     from pitxu.lib.speech_to_text.wrapper_raw_input_stream import WrapperRawInputStream
        #     # Correct format for Vosk is PCM 16khz 16bit mono
        #     self._raw_input_stream = WrapperRawInputStream(samplerate=self._dictate.samplerate,
        #                     blocksize = 0, 
        #                     device=self._dictate.device,
        #                     dtype="int16", 
        #                     channels=1,
        #                     callback=self._dictate.callback)
        # else:
        #     self._xlog.info("Loading Mocked Raw Input Stream (mic) for Speech-to-Text by Config")
        #     from pitxu.lib.speech_to_text.mocked_raw_input_stream import MockedRawInputStream
        #     self._raw_input_stream = MockedRawInputStream(config=self._xconfig, dictionary=self._xparams)

        # Initialise Chatbot
        self._xlog.debug("Initialising the Chatbot Client with language [" + self._xparams.get("language") + "]")
        self._chatbot = GeminiChatbot(config=self._xconfig, params=self._xparams)

    def _load_language_statics(self):

        # Load the greeting sentence
        self._xlog.debug("Load Greeting with language [" + self._xparams.get("language") + "]")
        self._greeting_sentence = self._xconfig.get("language.greeting." + self._xparams.get("language"))

        # Load the goodbye sentence
        self._xlog.debug("Load Goodbye with language [" + self._xparams.get("language") + "]")
        self._goodbye_sentence = self._xconfig.get("language.goodbye." + self._xparams.get("language"))

        # Load trigger words
        self._xlog.debug("Load Trigger words with language [" + self._xparams.get("language") + "]")
        self._trigger_words = self._xconfig.get("language.trigger_words." + self._xparams.get("language"))

        # Load trigger answers
        self._xlog.debug("Load Trigger answers with language [" + self._xparams.get("language") + "]")
        self._trigger_answers = self._xconfig.get("language.trigger_answers." + self._xparams.get("language"))

        # Compile exit words
        all_possible_exit_words = []
        for language, exit_words in dict(self._xconfig.get("language.exit_words")).items():
            for word in exit_words:
                if word not in all_possible_exit_words:
                    all_possible_exit_words.append(word)
        self._xlog.debug("Load ALL possible exit words " + str(all_possible_exit_words) + "")
        self._exit_words = all_possible_exit_words
    
    def _initialize_interactions(self):
        """
        Initialisation of the Interaction class, that manages output (TTS and displays)
        """

        self._xlog.info("Initialising Interaction class")
        self._interaction = Interaction(config=self._xconfig, params=self._xparams)

        # We start with the microphone muted.
        # At this point we don't have the Input Stream yet, just making sure that we start muted.
        self._interaction.mute_microphone()
    
    def _initialize_server(self):
        """
        Initializes the Server that accepts requests to the defined endpoints
        """

        if self._xconfig.get("server.enabled", False) and self._xconfig.get("app.execution_mode", "") in ["public", "server"]:
            self._xlog.info("Initializing Server as it is enabled by configuration.")
            params = deepcopy(self._xparams)
            params.set("output_interaction", self._interaction)
            params.set("chatbot", self._chatbot)
            params.set("chatbot_client_callbacks", self._chatbot_client_callbacks)
            self._server = Server(config=self._xconfig, params=params)
            self._server.initialize()
        else:
            self._xlog.info(f"Server is disabled by configuration (" +
                            f"enabled: {"TRUE" if self._xconfig.get('server.enabled', False) else "FALSE"}, " +
                            f"execution mode [{self._xconfig.get('app.execution_mode', '_NOT_SET_')}]"+
                            ") > not initializing it.")

    async def run(self):

        sw_init = self._stopwatch.start(name="init")

        # Execute the initial maintenance tasks
        self._maintenance.clean_previous_mocked_images()
        self._maintenance.clean_previous_generated_audios()
        self._maintenance.clean_previous_generated_audio_signal_plots()
        self._maintenance.clean_previous_generated_audio_spectrogram_plots()
        self._maintenance.clean_previous_generated_audio_fourier_transform_plots()

        # Initialise the Interaction manager, with Process pool, shared memory, displays, painter and TTS.
        self._initialize_interactions()
        # This is the only one that initializes BEFORE showing the phase. We need interaction() to be ready!
        self._interaction.show_init_phases(1, text="Interactions")

        # Startup splash. It should be understood as a "Loading..." screen.
        # We set it for 4s, but it may be overridden by the display config block for the related display.
        self._interaction.startup_splash(for_seconds=4.0)
        self._interaction.show_init_phases(2)


        # Initialize the case fan control and apply it.
        self._fan_control = FanControl(config=self._xconfig, params=self._xparams)
        self._fan_control_trigger_every_seconds = self._xconfig.get("gpio.cpu_temperature.control_interval_seconds", self._fan_control_trigger_every_seconds)
        self._fan_control.toggle_all_fans_by_temperature()

        # At this point, we better wait for all queues to be empty.
        # COMMENTED: Do we really need to wait for queues?
        # UNCOMMENTED: Hunting some Race Condition that makes the last 0.5s of the TTS to be input in SST.
        # self._interaction.wait_for_foreground_display_queue_to_empty()
        # self._interaction.show_init_phases(3, text="Foreground Display Queue Empty")

        # Initialise all classes that require a model. They go per language.
        self._interaction.show_init_phases(2, text="Models")
        self._load_models()

        # Load all language statics, like the exit words and the greeting / goodbye sentences
        self._interaction.show_init_phases(3, text="Language Statics")
        self._load_language_statics()

        try:
            # This is the samplerate that generates the chunks received in CaptureHandler.callback().
            #   In MacOS the microphone can't be set to an arbitrary samplerate that fits on us, so
            #   the config value for it must be -1 so that it gets inferred by de library.
            # Then the CaptureHeader will resample it to 16 kHz, and that's why the rest of components work
            #   under 16 kHz.
            # Set the samplerate that we're going to settle for the STT (ensure that the STT model has the EXACT SAME VALUE)
            # Fall back to what the Vosk's Kaldi Recognizer is using if the config value is not set.
            samplerate = self.get_samplerate()

            # Read from microphone.
            # with self._raw_input_stream() as input_stream:
            self._interaction.show_init_phases(4, text="Microphone")
            with sounddevice.RawInputStream(
                            #samplerate=self._dictate.samplerate,
                            # samplerate=16000, # Vosk works better with 16kHz, even if the mic supports higher rates.
                            samplerate=samplerate,
                            # blocksize=0, 
                            blocksize=1024,
                            device=self._dictate.device,
                            dtype="int16", 
                            channels=1,
                            # callback=self._dictate.callback) as input_stream:
                            callback=self._capture_handler.callback) as input_stream:
                
                self.log_summary("Raw Input Stream (Mic) initialized", [
                    ("Device", self._dictate.device),
                    ("Sample Rate", samplerate),
                    ("Block Size", "0 (default)"),
                    ("Channels", 1),
                    ("Data Type", "int16"),
                    ("Callback", "CaptureHandler.callback")
                ])
                
                # Welcome greeting
                sw_greeting = self._stopwatch.start(name="greeting")
                self._interaction.show_init_phases(5, text="Greeting")
                self._interaction.show_idle()
                self._interaction.say(self._greeting_sentence)
                self._xlog.debug("⏱️  Greeting: " + str(self._stopwatch.stop(sw_greeting)))

                # Set up of all the session context we need for the Chatbot and the MCP tools
                self._interaction.show_init_phases(6, text="Chatbot Session Manager")
                async with self._chatbot.get_session_manager() as chatbot_session_manager:

                    # Initialise the Chatbot async context with all the tools from the session manager
                    self._interaction.show_init_phases(7, text="Chatbot")
                    await self._chatbot.initialize_async(tools=chatbot_session_manager.tools)
                    self._chatbot_client_callbacks = self._chatbot.get_session_manager().get_client_callbacks_by_function_name()

                    # Initialise the Server that accepts requests to the defined endpoints.
                    self._interaction.show_init_phases(8, text="Server")
                    self._initialize_server()

                    # Clean background after initialisation.
                    # NOTE: I suspect double clear due to background & combined inheritance method execution.
                    #   Please check.
                    self._interaction.clear_background_display()
                    self._xlog.debug("⏱️  Initialisations: " + str(self._stopwatch.stop(sw_init)))

                    # Before we start with the loop, let's set the last interaction time to now
                    # It just started, there was a greating after all.
                    # Maybe the user wants to talk straight away without the trigger words.
                    self._last_interaction_datetime = datetime.now()
                    self._interaction.unmute_microphone(input_stream=input_stream)

                    question = ""
                    dictate_count = 0
                    answer_count = 0
                    while(not self._text_has_exit_intention(question) and self._is_pitxu_active):

                        # Check the things to do every minute
                        # This includes reminders checking and speaking them out.
                        self.do_every_minute_tasks()

                        # Check the things to do every second
                        # This includes checking for interaction holding time
                        self.do_every_second_tasks()

                        # Show idle screen in eInk if not already showing it
                        if not self._interaction.is_eink_in_idle_mode():
                            self._interaction.show_idle()

                        # Recognize what comes from the microphone
                        sw_dictate = self._stopwatch.continue_or_start(name="dictate" + str(dictate_count))
                        question = self._dictate.recognize()
                        if (question == None or question.strip() == ""):
                            # Nothing recognized, nothing to process.
                            continue

                        # Still here? Then something got recognised.
                        self._log_debug("💬 Recognised dictate: " + question)
                        self._xlog.debug("⏱️  Dictate " + str(dictate_count) + ": " + str(self._stopwatch.stop(sw_dictate)))
                        dictate_count += 1

                        # Mute microphone to avoid self-looping
                        self._interaction.mute_microphone(input_stream=input_stream)

                        # Initialize the answer that collects until interaction.
                        answer = None

                        # Analyze the question to see what to do.
                        text_has_exit_intention = self._text_has_exit_intention(question)
                        text_is_only_trigger_words = self._text_is_only_trigger_words(question)
                        text_initial_words_intend_to_trigger_interaction = self._text_initial_words_intend_to_trigger_interaction(question)
                        text_continues_ongoing_interaction = self._text_continues_ongoing_interaction(question)

                        # Avoid calling the Chatbot when we can exit directly.
                        if text_has_exit_intention and text_continues_ongoing_interaction:
                            # Just assume a goodbye
                            answer = self._goodbye_sentence
                        # Avoid calling the Chatbot when the text is only meant for waking up the system.
                        elif text_is_only_trigger_words:
                            # Randomly choose one of the trigger answers
                            import random
                            answer = random.choice(self._trigger_answers)
                        # Check if the text is meant to trigger or continue an interaction
                        # Same as before, but the question is passed to the chatbot.
                        elif text_initial_words_intend_to_trigger_interaction or text_continues_ongoing_interaction:

                            # Here we start with the Chatbot.
                            # -------------------------------

                            # We set it as busy in shared memory, so the Background Display can show the thinking effect
                            # Apparently, in the Raspberry Pi, the TTS starts too fast and the display does not get time
                            #   to react on the busy flag changes and be displayed on time.
                            self._interaction.show_thinking()
                            # I am going to try to show the question while thinking.
                            # It may give some time to the LCD to show the previous called thinking effect.
                            self._interaction.show_arbitrary_text_on_foreground_while_thinking(
                                icon="👤",
                                text=question,
                                font_size=24,
                            )
                            self._interaction.wait_for_background_display_queue_to_empty()
                            self._interaction.set_chatbot_busy()
                            chat_response: ChatbotResponse = await self._chatbot.ask_async(question)
                            self._tokens_counter += chat_response.metadata.total_token_count if chat_response.metadata and chat_response.metadata.total_token_count is not None else 0
                            self._interaction.unset_chatbot_busy()

                            try:
                                # We react on the answer received from the Chatbot, that may include function call responses and code blocks,
                                # or instructions for us to react, beyond the text to speak.
                                # For example, we may have to execute a Shutdown.
                                #
                                # Keep in mind that:
                                #   - repeating a question that involves a tool does not mean that in the second time the tool gets called.
                                #       It may just take the previous question and answer again.
                                #       There may not be a second function call response.
                                #   - by taking get_last(), we may be showing a previous response that does not fit to the question.
                                #       So the second time we may not be able to show the time on the screen, for example.
                                self._xlog.info(f"Reacting to a Chatbot answer: \n\t- Text: {chat_response.text}\n\t- Function Calls: {chat_response.function_call_history.get_names()}\n\t- Code blocks: {len(chat_response.code) if chat_response.code else 0}")
                                self.react_on_answer(chat_response=chat_response, input_stream=input_stream)
                            except Exception as e:
                                self._xlog.error("🛑 Error reacting to function call: " + str(e))
                            
                            # Finally, this is the answer string that moves on.
                            answer = chat_response.text

                            # This waiting happens BEFORE we reached the answering phase with the interaction.say().
                            # If the react_on_last_function_call() involved a show_arbitrary_text_on_foreground_while_speaking(),
                            # It will be waiting forever because the TTS has not started yet.
                            # - Commenting it out to see how it goes.
                            # - Uncommenting again because seems like the block happens in interaction.say() instead.
                            self._interaction.wait_for_foreground_display_queue_to_empty()

                        # Anything else is ignored.
                        else:
                            self._xlog.debug("💤 Ignoring dictate as no interaction was intended.")
                            # Removing the question, as it could be an unwanted trigger for exit.
                            question = ""

                        # Do we actually have any answer?
                        if answer is not None and answer.strip() != "":
                        
                            # Clean the answer first, just in case
                            answer = Text.remove_emojis(answer)
                            answer = Text.remove_markdown(answer)
                            answer = Text.replace_known_text(answer, self._xconfig.get("language.text_replacements." + self._xparams.get("language"), {}))

                            # Answer
                            sw_answer = self._stopwatch.start(name="answer" + str(answer_count))
                            self._interaction.say(answer)
                            self._xlog.debug("⏱️  Answer " + str(answer_count) + ": " + str(self._stopwatch.stop(sw_answer)))
                            answer_count += 1

                            # If we were communicating an error, it's over and start new
                            if self._interaction.is_chatbot_error():
                                self._interaction.unset_chatbot_error()
                            
                            # Last thing to do is to remember this as the last interaction.
                            # Has to happen at the very last otherwise the time is consumed by the possible answering process.
                            self._last_interaction_datetime = datetime.now()

                        # Unmute microphone to continue listening, but we'll wait an extra second to avoid immediate re-triggering.
                        # This second here makes the human-computer interaction worse.
                        # We need to find a way to stop the TTS audio from being input into the SST without intorducing such a delay.
                        # COMMENTED: Trying to activelly stop and start the input stream at the same mutin/unmuting the mic,
                        #   instead of waiting. 
                        # Hypothesis: When we activate the mic again, the buffer may contain data (the last spoken text) and it gets processed.
                        # time.sleep(1)
                        self._interaction.unmute_microphone(input_stream=input_stream)

                        # TEST: Try to release the CPU. I've seen it at 100%
                        time.sleep(0.5)
                    
                    # We arrived here because the user wanted to exit the main loop
                    # Make sure we leave the state properly
                    self._xlog.debug("💬 Exit intention detected in dictate. Exiting main loop.")
                    self._interaction.unset_eink_idle_mode()
                    self._interaction.wait_for_foreground_display_queue_to_empty()
                    self._interaction.wait_for_busy_foreground_display_to_idle()

        except KeyboardInterrupt:
            self._xlog.info("Pressed Control + C from main")
        except VoskException as ve:
            if not self._is_pitxu_active:
                self._xlog.warning("🛑 Exception detected in Main run loop, but Pitxu is already in the process of closing, so ignoring it: " + str(e))
                return
            self._xlog.error("🛑 VoskException detected in Main run loop: " + str(ve))
        except Exception as e:
            if not self._is_pitxu_active:
                self._xlog.warning("🛑 Exception detected in Main run loop, but Pitxu is already in the process of closing, so ignoring it: " + str(e))
                return
            self._xlog.error("🛑 Error in Main run loop: " + str(e))
            self._xlog.error(full_stack())  
        
        # However it happened, just close nicely.
        self.close_nicely()

    # ------------- End of the main method run() -------------
    
    def react_on_answer(self, chat_response: ChatbotResponse, input_stream: sounddevice.RawInputStream = None) -> None:
        """
        Reacts to the received answer beyond simply answering, like expressions, emotions, or actions.

        Args:
            chat_response (ChatbotResponse): The last response from the chatbot.
        
        Returns:
            None
        """

        if chat_response is None or \
                chat_response.function_call_history is None or \
                chat_response.function_call_history.get_last() is None or \
                not chat_response.function_call_history.get_last().has_response():
            return None
        

        # --- Code to react on function call ---

        # The idea here is to be able to use the hardware as part of the response, like moving eyes,
        #   or showing the hour in the Display if asked for the time...
        #
        # More importantly, this is the way to perform a proper close_nicely(), besides just
        #   shutting down or rebooting the system without caring.
        # For this last point to happen, we need to control the answer of the tool, give something
        #   specific to search for here.

        try:
            function_call_pair: FunctionCallPair = chat_response.function_call_history.get_last()
            if function_call_pair.has_response():
                self._xlog.debug("⚡️ Reacting to function call: " + str(function_call_pair.function_name))
                
                # We must start by the specifics. If none of them match, we go to the generic error handling.
                if function_call_pair.function_name == "error":
                    self._xlog.debug("🚨  Showing the ERROR in the eInk")

                    self._interaction.unset_eink_idle_mode()
                    self._interaction.wait_for_foreground_display_queue_to_empty()
                    self._interaction.wait_for_busy_foreground_display_to_idle()

                    self._interaction.show_arbitrary_text_on_foreground_while_speaking(
                        icon="🚨",
                        text=function_call_pair.function_response.response.get("result", "unknown"),
                        font_size=Canvas.FONT_SIZE_BIG)

                elif function_call_pair.function_name == "shutdown_local_machine":
                    self._xlog.debug("💤 Preparing for shutdown...")
                    self.close_nicely(avoid_final_exit=True)
                    try:
                        self._log_debug("Calling system shutdown now...")
                        call("sudo nohup shutdown -h now", shell=True)
                    except Exception as e:
                        self._xlog.error(f"Error during shutdown: {e}")
                elif function_call_pair.function_name == "reboot_local_machine":
                    self._xlog.debug("♻️  Preparing for reboot...")
                    self.close_nicely(avoid_final_exit=True)
                    try:
                        self._log_debug("Calling system shutdown now...")
                        call("sudo nohup reboot", shell=True)
                    except Exception as e:
                        self._xlog.error(f"Error during reboot: {e}")
                elif function_call_pair.function_name == "restart_system":
                    self._xlog.debug("🔄 Preparing to restart system...")
                    self.close_nicely()
                elif function_call_pair.function_name == "change_system_language":
                    self._xlog.debug("🌐 Preparing to change system language...")
                    result = function_call_pair.function_response.response.get("result", False)
                    intended_language = function_call_pair.function_call.arguments.get("new_language", "unknown")

                    if isinstance(result, bool) and result is False:
                        # This means that the language change failed internally. Most likely because we could not understand
                        # the requested language or it is not supported.
                        result = self._xconfig.get(f"language.language_not_supported.{self._xparams.get('language')}") % intended_language

                    if isinstance(result, str) and result not in self._supported_languages:
                        # This means that the result of the function returned anything but a supported language.
                        # Most likely is an error string. Simply let it say it.
                        self._xlog.debug("🚨 Showing the ERROR in the eInk")

                        self._interaction.unset_eink_idle_mode()
                        self._interaction.wait_for_foreground_display_queue_to_empty()
                        self._interaction.wait_for_busy_foreground_display_to_idle()

                        self._interaction.show_arbitrary_text_on_foreground_while_speaking(
                            icon="🚨",
                            text=result,
                            font_size=Canvas.FONT_SIZE_BIG)

                    else:
                        # We have here the new desired language code.
                        try:
                            # The very first thing is to set the language in the app's state.
                            self._state.set("language", result)
                            self._state.write_file()
                            self._xlog.debug(f"🌐 System language saved into app's state to [{result}].")

                            # If we close the app now, the micrphone is still muted, and gets conserved.
                            self._interaction.unmute_microphone(input_stream=input_stream)

                            # Now we close the app and give an exit code that indicates to the launcher that it just needs to restart the app.
                            self.close_nicely()
                            self._xlog.info("🌐 Exiting with code 42 to indicate language change")
                            # Feels like does not really exit, as logs show that afterwards it tries to unmute the microphone.
                            # Trying now to change from exit(42) to sys.exit(42)
                            sys.exit(42)
                        except Exception as e:
                            self._xlog.error(f"🛑 Failed to change system language to '{result}': {e}")

                    # Whatever we did, reactivate the microphone
                    # Note that for changing the language, we unmuted first and then exit, so in this case it should not hit here.
                    self._interaction.unmute_microphone(input_stream=input_stream)
                
                # Here we can parse the function response and act accordingly
                # For example, if the function call is to get the current time, we can display it on an eInk screen
                elif function_call_pair.function_name in self._chatbot_client_callbacks.keys():
                    # Generic callback execution for other functions that have a defined callback

                    value = function_call_pair.function_response.response.get("result", "unknown")
                    args = function_call_pair.function_call.arguments
                    self._xlog.debug("📺 Executing callback with value: " + str(value))
                    self._interaction.unset_eink_idle_mode()
                    self._interaction.wait_for_foreground_display_queue_to_empty()
                    self._interaction.wait_for_busy_foreground_display_to_idle()

                    # Here we call the callback from within the command, passing the context of `main._interaction` and the value
                    # Whatever happens, it's done there inside.
                    partial(
                        self._chatbot_client_callbacks[function_call_pair.function_name],
                        self._xlog,
                        self._interaction,
                        value,
                        args
                    )()
            
                # We should finish here. I didn't study yet cases when we have function calls AND anything else below.
                return

        except Exception as e:
            self._xlog.error("🛑 Error reacting to function call: " + str(e))
            self._xlog.debug(full_stack())
        
        # --- Code to react on chat_response more globally ---

        # The idea here is to cover answers that do not trigger a function call.
        # Lot of times is due to the chatbot repeating an answer, like "can you show me that code block again?"
        #   It simply picks it back from his history, but we still want to react on the answer.

        try:
            if chat_response.code is not None:
                self._xlog.debug(f"⚡️ Reacting to the first of {len(chat_response.code)} code blocks in the response")
                self._interaction.show_code_block_on_foreground(
                    code=chat_response.code[0],
                    for_seconds=10.0)
                # Sometimes it answers with code but no text, so we make it more human:
                if chat_response.text.strip() == "":
                    chat_response.text = self._xconfig.get("language.code.empty_answer_with_code." + self._xparams.get("language"))

        except Exception as e:
            self._xlog.error("🛑 Error reacting to code block in answer: " + str(e))
            self._xlog.debug(full_stack())

    def _text_has_exit_intention(self, text):
        return text in self._exit_words
    
    def _text_continues_ongoing_interaction(self, question: str) -> bool:
        # We may be in an ongoing interaction, so let's check the last interaction time
        # We must take in account the time spent talking
        if self._last_interaction_datetime is not None:
            seconds_since_last_interaction = (datetime.now() - self._last_interaction_datetime).total_seconds()
            if seconds_since_last_interaction <= self._seconds_to_hold_interaction_answer:
                return True
        
        # No ongoing interaction
        return False
    
    def _text_initial_words_intend_to_trigger_interaction(self, question: str) -> bool:
        # Let's consider that from what the user said, the first 5 words need to be one of the trigger words
        first_words = Text.remove_accents(" ".join(question.lower().strip().split(" ")[0:5]))
        for trigger_word in self._trigger_words:
            if trigger_word in first_words:
                return True
        
        # No trigger word found
        return False
    
    def _text_is_only_trigger_words(self, question: str) -> bool:
        # Let's consider that from what the user said, all words need to be one of the trigger words
        all_user_input = Text.remove_accents(question.lower().strip())
        for trigger_word in self._trigger_words:
            if trigger_word in all_user_input:
                return True
        
        # No trigger word found
        return False
    
    def close_nicely(self, avoid_final_exit=False):
        """
        Close the application nicely, cleaning up resources and saving state.

        Args:
            avoid_final_exit (bool): If True, avoids calling sys.exit() at the end. Useful when we want to shutdown or reboot after this method.
        """

        if not self._is_pitxu_active:
            self._log_debug("Already closed nicely, skipping.")
            return
        
        # Mark as not active anymore, so the rest of the app can see the state
        self._is_pitxu_active = False

        sw_closing = self._stopwatch.continue_or_start(name="closing")
        self._log_debug("Closing nicely...")

        # The chatbot may be in "Thinking" mode, unset it anyways.
        self._interaction.unset_chatbot_busy()

        # Reactivate the microphone because it keeps the state on shutdowns / reboots.
        # We never want it to be muted when starting.
        self._interaction.unmute_microphone()

        # In case that the user was speaking, clear the flag to avoid waiting forever.
        self._interaction.unset_user_is_speaking()

        # Persist state
        self.persist_state()

        # Stop Idle Mode if active
        if self._interaction.is_eink_in_idle_mode():
            self._interaction.unset_eink_idle_mode()

        # Clear the displays
        self.clear_displays()

        # Wait for all the queues and processes to get empty
        self._interaction.get_process_pool().get_memory_manager().force_all_flags_to_idle()
        self._interaction.wait_for_all_queues_to_empty()
        self._interaction.wait_for_all_busy_processes_to_idle()

        # Close the server
        if self._server is not None:
            self._server.close()

        # Close Vosk
        if self._dictate is not None:
            self._dictate.close()

        # Finish all related multiprocess stuff
        self._interaction.get_process_pool().finish_leftover_processes()

        # Finish interactions and related processes
        self._interaction.close()

        # ------ Final logs ------

        self._xlog.debug("⏱️  Closed: " + str(self._stopwatch.stop(sw_closing)))

        # Here comes anything that we want to do before leaving
        try:
            self._xlog.info("⏱️  Final Stopwatch report:\n" + self._stopwatch.stop_and_report())
            self._xlog.info("💡  Memory used: " + str(Memory.use(Memory.MEGABYTES)) + " MB")
            self._xlog.info("💰  Tokens used: " + str(self._tokens_counter))
        except (Exception, RuntimeError) as e:
            self._xlog.error("🛑 Error while logging final stats: " + str(e))

        # If requested, avoid the final sys.exit()
        if avoid_final_exit:
            self._xlog.info("Exiting nicely avoided final sys.exit() as requested.")
            return

        # And now, simply exit
        self._xlog.info("Exiting now. Goodbye!")
        sys.exit(0)
    
    def persist_state(self):

        self._state.set("tokens_counter", int(self._state.get("tokens_counter", 0)) + self._tokens_counter)
        self._state.write_file()
        self._xlog.debug("Persisted state to " + self._xconfig.get("storage.state_file"))
    
    def get_samplerate(self) -> int:
        device_samplerate = self.get_samplerate_from_device()
        samplerate = self._xconfig.get("speech-to-text.input_samplerate", device_samplerate)
        if samplerate == -1:
            samplerate = device_samplerate
        return samplerate
    
    def get_samplerate_from_device(self) -> int:
        device = self._xconfig.get("speech-to-text.input_device", None)
        if device is not None:
            device_info = sounddevice.query_devices(device, "input")
            # soundfile expects an int, sounddevice provides a float:
            return int(device_info["default_samplerate"])
        return 16000  # Default samplerate if no device is specified

    def clear_displays(self):
        if self._interaction.displays_are_combined():
            self._log_debug("Clearing the Combined Display.")
            self._interaction.clear_combined_display()
            return
        self._log_debug("Clearing the Foreground Display.")
        self._interaction.clear_foreground_display()
        self._log_debug("Clearing the Background Display.")
        self._interaction.clear_background_display()

    # ------- Stuff to do every minute -------

    def do_every_minute_tasks(self, input_stream: sounddevice.RawInputStream = None):
        current_minute = time.localtime().tm_min
        if current_minute != self._last_processed_minute:
            self._last_processed_minute = current_minute
            self._log_debug("🕐 New minute detected: " + str(current_minute) + ".")
            # Get the possible reminder for the current date and time
            date_str = datetime.now().strftime(Reminders.FORMAT_DATE)
            time_str = datetime.now().strftime(Reminders.FORMAT_TIME)
            reminder: dict = self._reminders.get_reminder(date_str, time_str)
            if reminder is not False:
                self._log_debug("📝 Reminder found for now: " + str(reminder))
                # Show reminder in eInk and say it
                reminder_text_for_speaking = self._xconfig.get("language.reminders.reminder_announcement." + self._xparams.get("language")) % reminder.get("text", "")
                self._interaction.unset_eink_idle_mode()
                self._interaction.wait_for_foreground_display_queue_to_empty()
                self._interaction.wait_for_busy_foreground_display_to_idle()
                self._interaction.show_arbitrary_text_on_foreground_while_speaking(
                    icon="📝",
                    text=reminder.get("text", ""),
                    font_size=Canvas.FONT_SIZE_BIG)
                self._interaction.mute_microphone(input_stream=input_stream)
                self._interaction.say(reminder_text_for_speaking)
                # TODO: Would be wonderful to integrate this spoken reminder to the history of the chatbot
                self._interaction.unmute_microphone(input_stream=input_stream)
                # Remove the reminder now that it's been announced
                self._reminders.delete_reminder(date_str, time_str)
                # Reset the last interaction time, as we just spoke
                self._last_interaction_datetime = datetime.now()
            
            # Every minute, log a bunch of metrics defined internally.
            # It also accepts a dict, that will be merged with the internal metrics.
            self._maintenance.log_metrics()
    
    # ------- Stuff to do every second -------

    def do_every_second_tasks(self):

        current_second = int(time.time())
        if current_second > self._last_processed_second:
            self._last_processed_second = current_second
            # COMMENTING: This log is too much verbose, as it happens every second.
            # self._log_debug("🕐 New second detected: " + str(time.localtime(current_second).tm_sec) + f".")

            # Control the fans according to the temperature, every some seconds is good enough for that.
            if self._fan_control_iterated_seconds < 0:
                self._fan_control.toggle_all_fans_by_temperature()
                self._fan_control_iterated_seconds += 1
            elif self._fan_control_iterated_seconds >= self._fan_control_trigger_every_seconds - 1:
                self._fan_control_iterated_seconds = -1
            else:
                self._fan_control_iterated_seconds += 1

            
            # If the background display is idle, show interaction holding percentage if applicable
            if not self._interaction.is_background_display_busy():
                # Show the interaction holding percentage if we're expecting an interaction
                if self._last_interaction_datetime is not None and not self._interaction.is_microphone_muted():
                    # Calculate how much left in percentages the time to hold the interaction
                    seconds_since_last_interaction = (datetime.now() - self._last_interaction_datetime).total_seconds()
                    if seconds_since_last_interaction <= self._seconds_to_hold_interaction_answer:
                        percent_left = int(100 - (seconds_since_last_interaction / self._seconds_to_hold_interaction_answer * 100))
                        self._last_processed_interaction_percentage = percent_left
                        self._xlog.debug("⏳ Waiting for an user interaction. " + str(percent_left) + "% time left.")
                        self._interaction.show_interaction_holding_percentage(percent_left)
                    elif self._last_processed_interaction_percentage >= 0:
                        # Interaction time is over, and we were showing the percentage
                        self._last_processed_interaction_percentage = -1
                        self._xlog.debug("⏳ Waiting for an user interaction is over. Clearing remainings.")
                        self._interaction.clear_background_display()
            else:
                self._xlog.debug("🤖 Background display is busy, not showing interaction holding percentage.")
            
            # vad_stats = self._capture_handler.get_vad_handler().get_stats()
            # dd(vad_stats)

            # self._dictate._preprocessor.on_speech_end()
                    
