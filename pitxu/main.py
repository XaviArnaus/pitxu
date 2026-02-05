from subprocess import call

from pyxavi import Logger, Config, Dictionary, Storage, full_stack, dd

import signal
from functools import partial

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.text import Text
from pitxu.lib.utils.stopwatch import Stopwatch
from pitxu.lib.utils.memory import Memory
from pitxu.lib.utils.maintenance import Maintenance
from pitxu.lib.utils.reminders import Reminders
from pitxu.lib.chatbot import GeminiChatbot
from pitxu.lib.interaction.interaction import Interaction

from pitxu.lib.canvas.canvas import Canvas

from pitxu.lib.speech_to_text import Vosk, VoskException
from pitxu.lib.objects import ChatbotResponse, FunctionCallPair


import sys
import sounddevice
import time
from datetime import datetime

class Main(PyXavi):

    _state: Storage = None
    
    _last_processed_minute: int = -1
    _last_processed_second: int = -1
    _last_processed_interaction_percentage: int = -1
    _last_interaction_datetime: datetime = None
    _seconds_to_hold_interaction_answer: int = 15

    _chatbot: GeminiChatbot = None
    _dictate: Vosk = None
    _raw_input_stream: sounddevice.RawInputStream = None

    _is_pitxu_active: bool = True

    _chatbot_client_callbacks: dict[str, callable] = None

    _maintenance: Maintenance = None
    _reminders: Reminders = None

    _stopwatch: Stopwatch = None
    _supported_languages: list = []
    _greeting_sentence: str = None
    _goodbye_sentence: str = None
    _trigger_answers: list[str] = []
    _exit_words: list = []
    _trigger_words: list = []
    _tokens_counter: int = 0

    COMM_DISPLAY = "display"
    COMM_MATRIX = "matrix"
    COMM_TTS = "tts"

    ENGLISH: str = "en-us"
    CATALAN: str = "ca"
    GERMAN: str = "de"
    SPANISH: str = "es"

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):

        super(Main, self).init_pyxavi(config=config, params=params)

        # Handle SIGTERM for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_sigterm)

        # Logger in params for other classes to use
        # self._xparams.set("logger", self._xlog)

        # Initialize State
        self._state = Storage(filename=self._xconfig.get("storage.path") + self._xconfig.get("storage.state_file"))

        # Initial Language. 1st from the state, then from the config, and last default to Catalan.
        language = self._state.get("language", config.get("app.default_language", self.CATALAN))
        self._xparams.set("language", language)

        # Initialize Maintenance utility
        self._maintenance = Maintenance(config=self._xconfig, params=self._xparams)

        # Supported Languages
        self._supported_languages = config.get("app.supported_languages")

        # The Reminders functionality
        self._reminders = Reminders(config=self._xconfig, params=self._xparams)

        # Stopwatch to measure times
        self._stopwatch = Stopwatch()
    
    def _handle_sigterm(self, sig, frame):
        """
        Handle SIGTERM signal

        This allows the service to stop gracefully when receiving a termination signal,
        that happens with systemctl stop or reboot commands.
        """
        self._xlog.warning('SIGTERM received in Main, closing nicely now...')
        self.close_nicely()

    def _load_models(self):
        
        # Initialise Speech-to-Text. This runs in the main process
        self._xlog.debug("Initialising the Speech-to-Text with language [" + self._xparams.get("language") + "]")
        self._dictate = Vosk(config=self._xconfig, params=self._xparams)

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

    async def run(self):

        sw_init = self._stopwatch.start(name="init")

        # Execute the initial maintenance tasks
        self._maintenance.clean_previous_mocked_images()

        # Initialise the Interaction manager, with Process pool, shared memory, displays, painter and TTS.
        self._initialize_interactions()
        self._interaction.show_init_phases(1)

        # Startup splash. It should be understood as a "Loading..." screen.
        # We set it for 4s, but it may be overridden by the display config block for the related display.
        self._interaction.startup_splash(for_seconds=4.0)
        self._interaction.show_init_phases(2)
        # ... yeah, "Loading", but I freeze the execution here.
        # Technically the system supports leaving the splash while loading, speaking (greetings) and stuff in background.
        # time.sleep(4)

        # At this point, we better wait for all queues to be empty.
        # This basically involves eInk (for the splash).
        # Matrix would also be related, but as we're showing the init phases, it's not that critical.
        # self._process_pool.wait_for_queue_to_empty(QUEUE_EINK)
        # COMMENTED: Do we really need to wait for queues?
        # UNCOMMENTED: Hunting some Race Condition that makes the last 0.5s of the TTS to be input in SST.
        self._interaction.wait_for_foreground_display_queue_to_empty()
        self._interaction.show_init_phases(3)

        # Initialise all classes that require a model. They go per language.
        self._load_models()
        self._interaction.show_init_phases(4)

        # Load all language statics, like the exit words and the greeting / goodbye sentences
        self._load_language_statics()
        self._interaction.show_init_phases(5)

        try:
            # Read from microphone.
            # with self._raw_input_stream() as input_stream:
            with sounddevice.RawInputStream(
                            samplerate=self._dictate.samplerate,
                            blocksize=0, 
                            device=self._dictate.device,
                            dtype="int16", 
                            channels=1,
                            callback=self._dictate.callback) as input_stream:
                self._interaction.show_init_phases(6)
                
                # Welcome greeting
                self._log_debug("Say Greetings")
                sw_greeting = self._stopwatch.start(name="greeting")
                self._interaction.show_idle()
                self._interaction.say(self._greeting_sentence)
                self._xlog.debug("⏱️  Greeting: " + str(self._stopwatch.stop(sw_greeting)))
                self._interaction.show_init_phases(7)

                # Set up of all the session context we need for the Chatbot and the MCP tools
                async with self._chatbot.get_session_manager() as chatbot_session_manager:
                    self._interaction.show_init_phases(8)

                    # Initialise the Chatbot async context with all the tools from the session manager
                    await self._chatbot.initialize_async(tools=chatbot_session_manager.tools)
                    self._chatbot_client_callbacks = self._chatbot.get_session_manager().get_client_callbacks_by_function_name()
                    self._interaction.show_init_phases(9)

                    # We consider this point as the end of the initialisation phases
                    # Clean the Matrix led from the points showing the init phases
                    # COMMENTED: I am hunting for a double CLEAN. Let me test.
                    # self._interaction.clear_background_display()

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
                            answer = chat_response.text
                            self._interaction.unset_chatbot_busy()
                            try:
                                self._log_debug("Function calls in the chat history: " + ", ".join(chat_response.function_call_history.get_names()))
                                if chat_response.function_call_history.get_last().has_response():
                                    self._log_debug("🗣️ Received function call response. Reacting.")
                                    # Shutdown and Reboot interrupt the flow and directly shutdown,
                                    # calling `close_nicely()` from there.
                                    # Keep in mind that:
                                    #   - here we may have played with BUSY flags.
                                    #   - repeating a question that involves a tool does not mean that the second time the tool gets called.
                                    #       It may just take the previous question and answer again.
                                    #       There may not be a second function call response.
                                    #       And by taking get_last(), we may be showing a previous response that does not fit to the question.
                                    #       So the second time we may not be able to show the time on the screen, for example.
                                    self.react_on_last_function_call(chat_response.function_call_history.get_last())
                            except Exception as e:
                                self._xlog.error("🛑 Error reacting to function call: " + str(e))

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
                    
                    # We arrived here because the user wanted to exit the main loop
                    # Make sure we leave the state properly
                    self._xlog.debug("💬 Exit intention detected in dictate. Exiting main loop.")
                    self._interaction.unset_eink_idle_mode()
                    self._interaction.wait_for_foreground_display_queue_to_empty()
                    self._interaction.wait_for_busy_foreground_display_to_idle()

        except KeyboardInterrupt:
            self._xlog.info("Pressed Control + C from main")
        except VoskException as ve:
            self._xlog.error("🛑 VoskException detected in Main run loop: " + str(ve))
        except Exception as e:
            self._xlog.error("🛑 Error in Main run loop: " + str(e))
            self._xlog.error(full_stack())  
        
        # However it happened, just close nicely.
        self.close_nicely()

    # ------------- End of the main method run() -------------
    
    def react_on_last_function_call(self, function_call_pair: FunctionCallPair, input_stream: sounddevice.RawInputStream = None) -> list[str]:
        """
        Reacts to the last function call beyond simply answering, like expressions, emotions, or actions.

        Args:
            function_call (FunctionCallPair): The last function call pair from the chatbot.
        
        Returns:
            list[str]: List of communications channels that should be ignored in the communication() method.
        """

        # The idea here is to be able to use the hardware as part of the response, like moving eyes,
        #   or showing the hour in the Display if asked for the time...
        #
        # More importantly, this is the way to perform a proper close_nicely(), besides just
        #   shutting down or rebooting the system without caring.
        # For this last point to happen, we need to control the answer of the tool, give something
        #   specific to search for here.

        try:

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

        except Exception as e:
            self._xlog.error("🛑 Error reacting to function call: " + str(e))
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

        # Persist state
        self.persist_state()

        # Stop Idle Mode if active
        if self._interaction.is_eink_in_idle_mode():
            self._interaction.unset_eink_idle_mode()

        # Clear the displays
        self.clear_displays()

        # Wait for all the queues and processes to get empty
        self._interaction.wait_for_all_queues_to_empty()
        self._interaction.wait_for_all_busy_processes_to_idle()

        # Close Vosk
        if self._dictate is not None:
            self._dictate.close()

        # Finish all related multiprocess stuff
        self._interaction.get_process_pool().finish_leftover_processes()

        # ------ Final logs ------

        self._xlog.debug("⏱️  Closed: " + str(self._stopwatch.stop(sw_closing)))

        # Here comes anything that we want to do before leaving
        self._xlog.info("⏱️  Final Stopwatch report:\n" + self._stopwatch.stop_and_report())
        self._xlog.info("💡  Memory used: " + str(Memory.use(Memory.MEGABYTES)) + " MB")
        self._xlog.info("💰  Tokens used: " + str(self._tokens_counter))

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
    
    # ------- Stuff to do every second -------

    def do_every_second_tasks(self):

        current_second = int(time.time())
        if current_second > self._last_processed_second:
            self._last_processed_second = current_second
            self._log_debug("🕐 New second detected: " + str(time.localtime(current_second).tm_sec) + f".")
            
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
                self._xlog.debug("🤖 Matrix is busy, not showing interaction holding percentage.")
                    