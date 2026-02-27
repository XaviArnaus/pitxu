from pyxavi import Logger, Config, Dictionary, Storage, full_stack, dd

import signal

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.text import Text
from pitxu.lib.utils.stopwatch import Stopwatch
from pitxu.lib.utils.memory import Memory
from pitxu.lib.utils.maintenance import Maintenance
from pitxu.lib.utils.reminders import Reminders
from pitxu.lib.chatbot.chatbot_session_manager import ChatbotSessionManager
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.interaction.reactions import Reactions
from pitxu.lib.canvas.canvas import Canvas
from pitxu.lib.speech_to_text.speech_to_text import SpeechToText, SpeechToTextException
from pitxu.lib.chatbot.generic_chatbot import GenericChatbot
from pitxu.lib.objects import ChatbotResponse
from pitxu.lib.gpio.buttons import Buttons

import sys
import sounddevice
import time
from datetime import datetime
import asyncio
import logging
from apscheduler.schedulers.background import BackgroundScheduler

class MainClientPTT(PyXavi):

    _state: Storage = None
    
    _last_processed_minute: int = -1
    _last_processed_second: int = -1
    _last_processed_interaction_percentage: int = -1
    _last_interaction_datetime: datetime = None
    _seconds_to_hold_interaction_answer: int = 15

    _chatbot: GenericChatbot = None
    _chatbot_session_manager: ChatbotSessionManager = None
    _dictate: SpeechToText = None
    _raw_input_stream: sounddevice.RawInputStream = None
    _buttons: Buttons = None
    _is_pitxu_active: bool = True
    _execution_mode: str = "client"

    _chatbot_client_callbacks: dict[str, callable] = None

    _interaction: Interaction = None
    _reactions: Reactions = None

    _scheduler: BackgroundScheduler = None
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

    ENGLISH: str = "en-us"
    CATALAN: str = "ca"
    GERMAN: str = "de"
    SPANISH: str = "es"

    PUSH_TO_TALK_BUTTON: str = "side"

    SCHEDULER_LIB_LOGLEVEL = logging.WARNING
    TZLOCAL_LIB_LOGLEVEL = logging.INFO

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):

        super(MainClientPTT, self).init_pyxavi(config=config, params=params)

        # Handle SIGTERM for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_sigterm)

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

        # Dependencies lib's log level
        self.SCHEDULER_LIB_LOGLEVEL = self._xconfig.get("libs_logger.scheduler.loglevel", self.SCHEDULER_LIB_LOGLEVEL)
        self.TZLOCAL_LIB_LOGLEVEL = self._xconfig.get("libs_logger.tzlocal.loglevel", self.TZLOCAL_LIB_LOGLEVEL)

    def _handle_sigterm(self, sig, frame):
        """
        Handle SIGTERM signal

        This allows the service to stop gracefully when receiving a termination signal,
        that happens with systemctl stop or reboot commands.
        """

        # TODO: Now that there is no loop, and there is a signal.pause() at the end of the run() method,
        #   we should check if this handler is still needed, and if it works as expected.
        self._xlog.warning('SIGTERM received in MainClient, closing nicely now...')
        self.close_nicely()
    
    def _initialize_speech_to_text(self):
        """
        Initializes the Speech-to-Text module that will call the server to transcribe the audio.
        """

        self._dictate = SpeechToText(config=self._xconfig, params=self._xparams)
        self._dictate.initialize()

    async def _initialize_chatbot(self):
        """
        Initializes the Generic Chatbot and the Session Manager and gathers the callbacks definition.
        that manages the session context for the Chatbot and the MCP tools.

        The idea is that we don't need the Chatbot,
        but it returns answers that may involve tools that we want to react on.
        """
        self._chatbot = GenericChatbot(config=self._xconfig, params=self._xparams)
        self._chatbot.initialize()

        chatbot_session_manager = ChatbotSessionManager(config=self._xconfig, params=self._xparams)
        await chatbot_session_manager.initialize()
        self._chatbot_client_callbacks = chatbot_session_manager.get_client_callbacks_by_function_name()
    
    def _initialize_buttons(self):
        """
        Initializes the Buttons module that will manage the physical buttons.
        """
        self._buttons = Buttons(config=self._xconfig, params=self._xparams)
        self._buttons.initialize_buttons()

        if self._buttons.buttons is not None and len(self._buttons.buttons) > 0:
            button_names = list(self._buttons.buttons.keys())
            self._xlog.info(f"Initialized buttons: {button_names}")

            if self.PUSH_TO_TALK_BUTTON not in button_names:
                self._xlog.warning(f"🟠 Push to talk button '{self.PUSH_TO_TALK_BUTTON}' not found in initialized buttons: {button_names}. " +
                                   f"Assigning Push To Talk functionality to the first button in the list: {button_names[0]}")
                self.PUSH_TO_TALK_BUTTON = button_names[0]
        else:
            self._xlog.error("No buttons initialized. Push to Talk functionality will not be available. Closing.")
            self.close_nicely(avoid_final_exit=False)

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
    
    def _initialize_reactions(self, input_stream: sounddevice.RawInputStream = None):
        """
        Initialisation of the Reactions class, that manages the reactions to the Chatbot answers and tool calls.
        """

        self._xlog.info("Initialising Reactions class")

        params: Dictionary = Dictionary({
            "interaction": self._interaction,
            "client_callbacks": self._chatbot_client_callbacks,
            "close_nicely_callback": self.close_nicely,
            "input_stream": input_stream
        })
        self._reactions = Reactions(config=self._xconfig, params=params)
    
    def _initialize_schedulers(self):
        """
        Initialisation of the schedulers for the tasks that need to be executed by time, like the reminders.
        """

        self._xlog.info("Initialising Schedulers")

        # self._scheduler = sched.scheduler(timefunc=time.time, delayfunc=time.sleep)
        # self._scheduler.enter(60.0, 1, self.do_every_minute_tasks)
        # self._scheduler.enter(1.0, 1, self.do_every_second_tasks)
        # self._scheduler.run(blocking=False)

        self._scheduler = BackgroundScheduler()
        logging.getLogger("apscheduler").setLevel(self.SCHEDULER_LIB_LOGLEVEL)
        logging.getLogger("tzlocal").setLevel(self.TZLOCAL_LIB_LOGLEVEL)
        self._scheduler.add_job(self.do_every_minute_tasks, 'interval', minutes=1, args=[None])
        # At the moment, we don't need to run tasks every second.
        # self._scheduler.add_job(self.do_every_second_tasks, 'interval', seconds=1)
        self._scheduler.start()

    async def run(self):

        sw_init = self._stopwatch.start(name="init")

        # Execute the initial maintenance tasks
        self._maintenance.clean_previous_mocked_images()
        self._maintenance.clean_previous_generated_audios()

        # Initialise the Interaction manager, with Process pool, shared memory, displays, painter and TTS.
        self._initialize_interactions()
        # This is the only one that initializes BEFORE showing the phase. We need interaction() to be ready!
        self._interaction.show_init_phases(1, text="💬 Interactions")

        # Startup splash. It should be understood as a "Loading..." screen.
        # We set it for 4s, but it may be overridden by the display config block for the related display.
        # self._interaction.startup_splash(for_seconds=4.0)

        # Initialise the SpeechToText module,
        # that will be responsible for recognizing the audio and sending it to the server for transcription.
        self._interaction.show_init_phases(2, text="🗣️  Speech-to-Text")
        self._initialize_speech_to_text()

        # Load all language statics, like the exit words and the greeting / goodbye sentences
        self._interaction.show_init_phases(3, text="🔤 Language Statics")
        self._load_language_statics()

        # Initialise the Buttons module
        self._interaction.show_init_phases(4, text="🔘 Buttons")
        self._initialize_buttons()

        try:
            # Read from microphone.
            # with self._raw_input_stream() as input_stream:
            self._interaction.show_init_phases(5, text="🎙️  Microphone")
            # Vosk wants the following parameters: 16kHz, mono, 16 bit.
            with sounddevice.RawInputStream(
                            # samplerate=self._dictate.samplerate,
                            # Tried like this, the server side is unable to transcribe.
                            # samplerate=16000,
                            samplerate=44100,
                            blocksize=0, 
                            device=self._dictate.device,
                            dtype="int16", 
                            channels=1,
                            callback=self._dictate.callback) as input_stream:
                
                # Welcome greeting
                sw_greeting = self._stopwatch.start(name="greeting")
                self._interaction.show_init_phases(6, text="👋 Greeting")
                self._interaction.show_idle()
                self._interaction.say(self._greeting_sentence)
                self._xlog.debug("⏱️  Greeting: " + str(self._stopwatch.stop(sw_greeting)))

                # Load the Chatbot Callbacks definitions,
                #   that are needed to react on the possible tool calls in the answers.
                self._interaction.show_init_phases(7, text="🤖 Chatbot")
                await self._initialize_chatbot()

                # Before we start with the loop, let's set the last interaction time to now
                # It just started, there was a greating after all.
                # Maybe the user wants to talk straight away without the trigger words.
                self._last_interaction_datetime = datetime.now()

                # Initialize the Reactions class
                self._interaction.show_init_phases(8, text="⚡️ Reactions")
                self._initialize_reactions(input_stream=input_stream)

                # The callback approach
                # ---------------------
                #
                # The idea here is to set all callbacks for all actions, to avoid running a forever loop.
                #
                self._interaction.show_init_phases(9, text="↩️  PTT Callbacks")

                # Initialize the flags
                # question = ""
                dictate_count = 0
                answer_count = 0
                recording_audio = False

                # The callbacks are the old loop iteration, happening when we want it to react (that's the button pressed/released for PTT).

                # The actual idea was to have 2 different callbacks for the PPT button, one for the press and another for the release,
                # But I was unable to make it work correctly with the gpiozero buttons callback support.
                # I found that both were being called at the same time no matter what, so I ended it setting the same callback for both
                # and checking the button state inside the callback to know if it's a press or a release.
                # Also I did tests with the "when_held" besides "when pressed", and work as expected but still calls the callback 
                # when pressing, repeating the call to the callback, and being then weak on the control.

                def on_button_interact(button, cls: MainClientPTT = None, button_name: str = None, flags: dict = {}):

                    cls._log_debug(f"🎙️ Button [{button_name}] interact callback triggered: \n" +
                                    "   - " + ("recording audio." if flags.get("recording_audio", False) else "Not recording audio.") + "\n" +
                                    "   - Button state is " + ("PRESSED." if cls._buttons.is_pressed(button_name) else "RELEASED."))

                    # Init.
                    question = ""
                    is_pressed = cls._buttons.is_pressed(button_name)

                    if is_pressed and not flags.get("recording_audio", False):

                        cls._log_debug(f"🎙️ Starting to record audio for button [{button_name}] press.")
                        flags["recording_audio"] = True
                        cls._interaction.unmute_microphone(input_stream=input_stream)

                    if not is_pressed and flags.get("recording_audio", False):
                    
                        cls._log_debug(f"🎙️ Stopping audio registration for button [{button_name}] release and starting recognition.")
                        flags["recording_audio"] = False
                        cls._interaction.mute_microphone(input_stream=input_stream)
                        
                        # Place some feedback to the user so that it knows that the audio has been registered and is being processed.
                        cls._interaction.show_thinking()
                        cls._interaction.set_chatbot_busy()

                        # Recognize what comes from the microphone
                        sw_dictate = cls._stopwatch.continue_or_start(name="dictate" + str(flags.get("dictate_count", 0)))
                        error = None
                        try:
                            question = cls._dictate.recognize()
                        except SpeechToTextException as stte:

                            if len(stte.args) > 1 and stte.args[1] is not None and isinstance(stte.args[1], dict):
                                error = stte.args[1].get("error", "Unknown error during transcription")
                            else:
                                error = str(stte)

                            cls._xlog.error("🛑 Error during SpeechToText recognition in MainClientPTT: " + error)
                            question = None

                        # We have the answer, unset the busy state.
                        cls._interaction.unset_chatbot_busy()

                        if question is None:
                            cls._xlog.debug(f"🎙️ Nothing recognized")
                            if error is None:
                                # This way we trigger a UX feedback saying that nothing was recognized.
                                cls._interaction.show_error(
                                    text="Nothing recognized",
                                    for_seconds=3
                                )
                                # Also we can make it say it.
                                cls._interaction.say(cls._xconfig.get("language.transcription_error." + cls._xparams.get("language"), "I didn't understand you."))
                    
                        # Let's show any possible error in the screen
                        if error is not None:
                            cls._interaction.show_error(
                                text=error,
                                for_seconds=3
                            )
                    
                    # If at this point we still not have a question, finish the iteration here and loop again.
                    if (question is None or (question is not None and question.strip() == "")):
                        # Nothing recognized, nothing to process.
                        return

                    # Still here? Then something got recognised.
                    cls._log_debug("💬 Recognised dictate: " + question)
                    if sw_dictate is not None:
                        cls._xlog.debug("⏱️  Dictate " + str(flags.get("dictate_count", 0)) + ": " + str(cls._stopwatch.stop(sw_dictate)))
                    else:
                        cls._xlog.warning("🟠 Dictate " + str(flags.get("dictate_count", 0)) + ": Stopwatch was not started for this dictate. That should not happen.")
                    flags["dictate_count"] = flags.get("dictate_count", 0) + 1

                    # Initialize the answer that collects until interaction.
                    answer = None

                    # Analyze the question to see what to do.
                    text_has_exit_intention = cls._text_has_exit_intention(question)

                    # Avoid calling the Chatbot when we can exit directly.
                    if text_has_exit_intention:
                        # Just assume a goodbye
                        answer = cls._goodbye_sentence

                    else:

                        # Here we start with the Chatbot.
                        # -------------------------------

                        # We set it as busy in shared memory, so the Background Display can show the thinking effect
                        # Apparently, in the Raspberry Pi, the TTS starts too fast and the display does not get time
                        #   to react on the busy flag changes and be displayed on time.
                        cls._interaction.show_thinking()
                        # I am going to try to show the question while thinking.
                        # It may give some time to the LCD to show the previous called thinking effect.
                        cls._interaction.show_arbitrary_text_on_foreground_while_thinking(
                            icon="👤",
                            text=question,
                            font_size=24,
                        )
                        cls._interaction.wait_for_background_display_queue_to_empty()
                        cls._interaction.set_chatbot_busy()
                        chat_response: ChatbotResponse = asyncio.run(cls._chatbot.ask_async(question))
                        cls._interaction.unset_chatbot_busy()

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
                            cls._xlog.info(f"Reacting to a Chatbot answer: \n\t- Text: {chat_response.text}\n\t- Function Calls: {chat_response.function_call_history.get_names()}\n\t- Code blocks: {len(chat_response.code) if chat_response.code else 0}")
                            cls._reactions.react_on_answer(chat_response=chat_response)
                        except Exception as e:
                            cls._xlog.error("🛑 Error reacting to function call: " + str(e))
                        
                        # Finally, this is the answer string that moves on.
                        answer = chat_response.text

                        # This waiting happens BEFORE we reached the answering phase with the interaction.say().
                        # If the react_on_last_function_call() involved a show_arbitrary_text_on_foreground_while_speaking(),
                        # It will be waiting forever because the TTS has not started yet.
                        # - Commenting it out to see how it goes.
                        # - Uncommenting again because seems like the block happens in interaction.say() instead.
                        cls._interaction.wait_for_foreground_display_queue_to_empty()

                    # Do we actually have any answer?
                    if answer is not None and answer.strip() != "":
                    
                        # Clean the answer first, just in case
                        answer = Text.remove_emojis(answer)
                        answer = Text.remove_markdown(answer)
                        answer = Text.replace_known_text(answer, cls._xconfig.get("language.text_replacements." + cls._xparams.get("language"), {}))

                        # Answer
                        sw_answer = cls._stopwatch.start(name="answer" + str(flags.get("answer_count", 0)))
                        cls._interaction.say(answer)
                        cls._xlog.debug("⏱️  Answer " + str(flags.get("answer_count", 0)) + ": " + str(cls._stopwatch.stop(sw_answer)))
                        flags["answer_count"] += 1

                        # If we were communicating an error, it's over and start new
                        if cls._interaction.is_chatbot_error():
                            cls._interaction.unset_chatbot_error()
                        
                        # Last thing to do is to remember this as the last interaction.
                        # Has to happen at the very last otherwise the time is consumed by the possible answering process.
                        cls._last_interaction_datetime = datetime.now()
                    
                    # Now that we spoke the answer, behave according to the exit intention of the text.
                    if text_has_exit_intention:
                        cls._xlog.info("Exit intention detected in the transcription, closing MainClientPTT nicely.")
                        cls.close_nicely()

                # Embedding the general flags into a var to be passed into the callbacks.
                flags = {
                    "recording_audio": recording_audio,
                    "dictate_count": dictate_count,
                    "answer_count": answer_count,
                }

                # Set the press callback for the Push To Talk button
                self._buttons.set_pressed_callback(
                    button_name=self.PUSH_TO_TALK_BUTTON, 
                    callback=on_button_interact, 
                    kargs={
                        "cls": self,
                        "button_name": self.PUSH_TO_TALK_BUTTON,
                        "flags": flags
                    })
                # Set the release callback for the Push To Talk button
                self._buttons.set_released_callback(
                    button_name=self.PUSH_TO_TALK_BUTTON, 
                    callback=on_button_interact, 
                    kargs={
                        "cls": self,
                        "button_name": self.PUSH_TO_TALK_BUTTON,
                        "flags": flags
                    })

                # Just to support the mocked buttons, we start listening for events.
                self._buttons.start_listening()

                # TODO: We need to have a way to set callbacks by time, for the reminders and the maintenance tasks. 
                #   That would be the equivalent of the do_every_minute_tasks() and do_every_second_tasks() that we had in the loop.
                self._interaction.show_init_phases(10, text="⏱️  Schedulers")
                self._initialize_schedulers()

                # Clean background after initialisation.
                self._log_debug("Clearing displays after initialisation.")
                self._interaction.clear_combined_display()
                self._interaction.wait_for_all_queues_to_empty()
                self._xlog.debug("⏱️  Initialisations: " + str(self._stopwatch.stop(sw_init)))

                # At this point, all initialisations are done.
                # Because we work this callbacks, this is the last point before the signal.pause() stops and waits
                self._interaction.show_init_phases(11, text="✅ Ready")
                self._xlog.info("🟢 All initialisations done, entering idle state, waiting for interactions...")

                # Wait indefinitely until a signal is received (like SIGTERM for graceful shutdown)
                signal.pause()

                # Now that the pause has resumed, means that we are meant to close.
                # Make sure we leave the state properly
                self._xlog.debug("🏁 Exit signal detected.")
                self._interaction.unset_eink_idle_mode()
                self._interaction.wait_for_foreground_display_queue_to_empty()
                self._interaction.wait_for_busy_foreground_display_to_idle()

                # --------- End of the callback approach ---------

        except KeyboardInterrupt:
            self._xlog.info("Pressed Control + C from MainClient")
        except Exception as e:
            self._xlog.error("🛑 Error in MainClientPTT run loop: " + str(e))
            self._xlog.error(full_stack())  
        
        # However it happened, just close nicely.
        self.close_nicely()

    # ------------- End of the main method run() -------------

    def _text_has_exit_intention(self, text):
        return text in self._exit_words
    
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

        # The scheduler contains a thread, so close it properly.
        self._scheduler.shutdown()

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