from subprocess import call
import sched

from pyxavi import Logger, Config, Dictionary, Storage, full_stack, dd

import signal
from functools import partial

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.text import Text
from pitxu.lib.utils.stopwatch import Stopwatch
from pitxu.lib.utils.memory import Memory
from pitxu.lib.utils.maintenance import Maintenance
from pitxu.lib.utils.reminders import Reminders
from pitxu.lib.chatbot.chatbot_session_manager import ChatbotSessionManager
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.canvas.canvas import Canvas
from pitxu.lib.speech_to_text.speech_to_text import SpeechToText, SpeechToTextException
from pitxu.lib.chatbot.generic_chatbot import GenericChatbot
from pitxu.lib.objects import ChatbotResponse, FunctionCallPair
from pitxu.lib.gpio.buttons import Buttons

import sys
import sounddevice
import time
from datetime import datetime
import asyncio

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

    _scheduler: sched.scheduler = None
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

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):

        super(MainClientPTT, self).init_pyxavi(config=config, params=params)

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
    
    def _handle_sigterm(self, sig, frame):
        """
        Handle SIGTERM signal

        This allows the service to stop gracefully when receiving a termination signal,
        that happens with systemctl stop or reboot commands.
        """
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

    async def run(self):

        sw_init = self._stopwatch.start(name="init")

        # Execute the initial maintenance tasks
        self._maintenance.clean_previous_mocked_images()
        self._maintenance.clean_previous_generated_audios()

        # Initialise the Interaction manager, with Process pool, shared memory, displays, painter and TTS.
        self._initialize_interactions()
        # This is the only one that initializes BEFORE showing the phase. We need interaction() to be ready!
        self._interaction.show_init_phases(1, text="Interactions")

        # Startup splash. It should be understood as a "Loading..." screen.
        # We set it for 4s, but it may be overridden by the display config block for the related display.
        self._interaction.startup_splash(for_seconds=4.0)

        # At this point, we better wait for all queues to be empty.
        # COMMENTED: Do we really need to wait for queues?
        # UNCOMMENTED: Hunting some Race Condition that makes the last 0.5s of the TTS to be input in SST.
        # self._interaction.wait_for_foreground_display_queue_to_empty()
        # self._interaction.show_init_phases(3, text="Foreground Display Queue Empty")

        # Initialise the SpeechToText module,
        # that will be responsible for recognizing the audio and sending it to the server for transcription.
        self._interaction.show_init_phases(2, text="Speech-to-Text")
        self._initialize_speech_to_text()

        # Load all language statics, like the exit words and the greeting / goodbye sentences
        self._interaction.show_init_phases(3, text="Language Statics")
        self._load_language_statics()

        # Initialise the Buttons module
        self._interaction.show_init_phases(4, text="Buttons")
        self._initialize_buttons()

        try:
            # Read from microphone.
            # with self._raw_input_stream() as input_stream:
            self._interaction.show_init_phases(5, text="Microphone")
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
                self._interaction.show_init_phases(6, text="Greeting")
                self._interaction.show_idle()
                self._interaction.say(self._greeting_sentence)
                self._xlog.debug("⏱️  Greeting: " + str(self._stopwatch.stop(sw_greeting)))

                # Load the Chatbot Callbacks definitions,
                #   that are needed to react on the possible tool calls in the answers.
                self._interaction.show_init_phases(7, text="Chatbot")
                await self._initialize_chatbot()

                # Before we start with the loop, let's set the last interaction time to now
                # It just started, there was a greating after all.
                # Maybe the user wants to talk straight away without the trigger words.
                self._last_interaction_datetime = datetime.now()


                # The callback approach
                # ---------------------
                #
                # The idea here is to set all callbacks for all actions, to avoid running a forever loop.
                #
                self._interaction.show_init_phases(8, text="PTT Callbacks")

                # Initialize the flags
                # question = ""
                dictate_count = 0
                answer_count = 0
                recording_audio = False

                # The callbacks are the actual loop iteration, happening when we want it to react (that's the button pressed/released).
                # The old loop is the on_release() basically.

                def on_push_to_talk_pressed(button, cls: MainClientPTT = None, button_name: str = None, flags: dict = {}):
                    cls._log_debug(f"🎙️ Button [{button_name}] pressed callback triggered. We were " +
                                    ("recording audio." if flags.get("recording_audio", False) else "Not recording audio."))
                    
                    if not flags.get("recording_audio", False):
                        cls._log_debug(f"🎙️ Starting to record audio for button [{button_name}] press.")
                        flags["recording_audio"] = True
                        cls._interaction.unmute_microphone(input_stream=input_stream)

                def on_push_to_talk_released(button, cls: MainClientPTT = None, button_name: str = None, flags: dict = {}):
                    cls._log_debug(f"🎙️ Button [{button_name}] released callback triggered. We were " +
                                    ("recording audio." if flags.get("recording_audio", False) else "NOT recording audio."))

                    # Initialize the question that travels the flow
                    question = ""
                    
                    if flags.get("recording_audio", False):
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
                            cls.react_on_answer(chat_response=chat_response, input_stream=input_stream)
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

                # Embedding the general flags into a var to be passed into the callbacks.
                flags = {
                    "recording_audio": recording_audio,
                    "dictate_count": dictate_count,
                    "answer_count": answer_count,
                }
                # Set the press callback for the Push To Talk button
                self._buttons.set_pressed_callback(
                    button_name=self.PUSH_TO_TALK_BUTTON, 
                    callback=on_push_to_talk_pressed, 
                    kargs={
                        "cls": self,
                        "button_name": self.PUSH_TO_TALK_BUTTON,
                        "flags": flags
                    })
                # Set the release callback for the Push To Talk button
                self._buttons.set_released_callback(
                    button_name=self.PUSH_TO_TALK_BUTTON, 
                    callback=on_push_to_talk_released, 
                    kargs={
                        "cls": self,
                        "button_name": self.PUSH_TO_TALK_BUTTON,
                        "flags": flags
                    })

                # Just to support the mocked buttons, we start listening for events.
                self._buttons.start_listening()

                # TODO: We need to have a way to set callbacks by time, for the reminders and the maintenance tasks. 
                #   That would be the equivalent of the do_every_minute_tasks() and do_every_second_tasks() that we had in the loop.
                self._interaction.show_init_phases(9, text="Schedulers")
                self._scheduler = sched.scheduler(timefunc=time.time, delayfunc=time.sleep)
                self._scheduler.enter(60.0, 1, self.do_every_minute_tasks)
                self._scheduler.enter(1.0, 1, self.do_every_second_tasks)
                self._scheduler.run()

                # Clean background after initialisation.
                # NOTE: I suspect double clear due to background & combined inheritance method execution.
                #   Please check.
                self._interaction.clear_combined_display()
                self._interaction.wait_for_all_queues_to_empty()
                self._xlog.debug("⏱️  Initialisations: " + str(self._stopwatch.stop(sw_init)))

                # Wait indefinitely until a signal is received (like SIGTERM for graceful shutdown)
                signal.pause()

                # Now that the pause has resumed, means that we are meant to close.
                self.close_nicely()

                # --------- End of the callback approach ---------

                # question = ""
                # dictate_count = 0
                # answer_count = 0
                # recording_audio = False
                # while(not self._text_has_exit_intention(question) and self._is_pitxu_active):

                #     # Check the things to do every minute
                #     # This includes reminders checking and speaking them out.
                #     self.do_every_minute_tasks()

                #     # Check the things to do every second
                #     # This includes checking for interaction holding time
                #     self.do_every_second_tasks()

                #     # Show idle screen in eInk if not already showing it
                #     # if not self._interaction.is_eink_in_idle_mode():
                #     #     self._interaction.show_idle()

                #     # The question gets a value when we transcribe successfully. Otherwise, should be always None.
                #     question = None

                #     # Check if the push to talk button is pressed to record the audio
                #     sw_dictate = None
                #     if self._buttons.is_pressed(self.PUSH_TO_TALK_BUTTON) and not recording_audio:
                #         self._log_debug("🎙️ Push to talk button is pressed, registering audio.")
                #         recording_audio = True
                #         self._interaction.unmute_microphone(input_stream=input_stream)
                    
                #     # Check if the push to talk button is released to stop recording audio
                #     if not self._buttons.is_pressed(self.PUSH_TO_TALK_BUTTON) and recording_audio:
                #         self._log_debug("🎙️ Push to talk button is released, stopping audio registration and starting recognition.")
                #         recording_audio = False
                #         self._interaction.mute_microphone(input_stream=input_stream)
                        
                #         # Place some feedback to the user so that it knows that the audio has been registered and is being processed.
                #         self._interaction.show_thinking()
                #         self._interaction.set_chatbot_busy()

                #         # Recognize what comes from the microphone
                #         sw_dictate = self._stopwatch.continue_or_start(name="dictate" + str(dictate_count))
                #         question = self._dictate.recognize()

                #         # We have the answer, unset the busy state.
                #         self._interaction.unset_chatbot_busy()

                #         if question is None:
                #             self._xlog.debug(f"🎙️ Nothing recognized")
                                            
                #     # If at this point we still not have a question, finish the iteration here and loop again.
                #     if (question is None or (question is not None and question.strip() == "")):
                #         # Nothing recognized, nothing to process.
                #         continue

                #     # Still here? Then something got recognised.
                #     self._log_debug("💬 Recognised dictate: " + question)
                #     if sw_dictate is not None:
                #         self._xlog.debug("⏱️  Dictate " + str(dictate_count) + ": " + str(self._stopwatch.stop(sw_dictate)))
                #     else:
                #         self._xlog.warning("🟠 Dictate " + str(dictate_count) + ": Stopwatch was not started for this dictate. That should not happen.")
                #     dictate_count += 1

                #     # Initialize the answer that collects until interaction.
                #     answer = None

                #     # Analyze the question to see what to do.
                #     text_has_exit_intention = self._text_has_exit_intention(question)

                #     # Avoid calling the Chatbot when we can exit directly.
                #     if text_has_exit_intention:
                #         # Just assume a goodbye
                #         answer = self._goodbye_sentence

                #     else:

                #         # Here we start with the Chatbot.
                #         # -------------------------------

                #         # We set it as busy in shared memory, so the Background Display can show the thinking effect
                #         # Apparently, in the Raspberry Pi, the TTS starts too fast and the display does not get time
                #         #   to react on the busy flag changes and be displayed on time.
                #         self._interaction.show_thinking()
                #         # I am going to try to show the question while thinking.
                #         # It may give some time to the LCD to show the previous called thinking effect.
                #         self._interaction.show_arbitrary_text_on_foreground_while_thinking(
                #             icon="👤",
                #             text=question,
                #             font_size=24,
                #         )
                #         self._interaction.wait_for_background_display_queue_to_empty()
                #         self._interaction.set_chatbot_busy()
                #         chat_response: ChatbotResponse = await self._chatbot.ask_async(question)
                #         self._interaction.unset_chatbot_busy()

                #         try:
                #             # We react on the answer received from the Chatbot, that may include function call responses and code blocks,
                #             # or instructions for us to react, beyond the text to speak.
                #             # For example, we may have to execute a Shutdown.
                #             #
                #             # Keep in mind that:
                #             #   - repeating a question that involves a tool does not mean that in the second time the tool gets called.
                #             #       It may just take the previous question and answer again.
                #             #       There may not be a second function call response.
                #             #   - by taking get_last(), we may be showing a previous response that does not fit to the question.
                #             #       So the second time we may not be able to show the time on the screen, for example.
                #             self._xlog.info(f"Reacting to a Chatbot answer: \n\t- Text: {chat_response.text}\n\t- Function Calls: {chat_response.function_call_history.get_names()}\n\t- Code blocks: {len(chat_response.code) if chat_response.code else 0}")
                #             self.react_on_answer(chat_response=chat_response, input_stream=input_stream)
                #         except Exception as e:
                #             self._xlog.error("🛑 Error reacting to function call: " + str(e))
                        
                #         # Finally, this is the answer string that moves on.
                #         answer = chat_response.text

                #         # This waiting happens BEFORE we reached the answering phase with the interaction.say().
                #         # If the react_on_last_function_call() involved a show_arbitrary_text_on_foreground_while_speaking(),
                #         # It will be waiting forever because the TTS has not started yet.
                #         # - Commenting it out to see how it goes.
                #         # - Uncommenting again because seems like the block happens in interaction.say() instead.
                #         self._interaction.wait_for_foreground_display_queue_to_empty()

                #     # Do we actually have any answer?
                #     if answer is not None and answer.strip() != "":
                    
                #         # Clean the answer first, just in case
                #         answer = Text.remove_emojis(answer)
                #         answer = Text.remove_markdown(answer)
                #         answer = Text.replace_known_text(answer, self._xconfig.get("language.text_replacements." + self._xparams.get("language"), {}))

                #         # Answer
                #         sw_answer = self._stopwatch.start(name="answer" + str(answer_count))
                #         self._interaction.say(answer)
                #         self._xlog.debug("⏱️  Answer " + str(answer_count) + ": " + str(self._stopwatch.stop(sw_answer)))
                #         answer_count += 1

                #         # If we were communicating an error, it's over and start new
                #         if self._interaction.is_chatbot_error():
                #             self._interaction.unset_chatbot_error()
                        
                #         # Last thing to do is to remember this as the last interaction.
                #         # Has to happen at the very last otherwise the time is consumed by the possible answering process.
                #         self._last_interaction_datetime = datetime.now()
                
                # # We arrived here because the user wanted to exit the main loop
                # # Make sure we leave the state properly
                # self._xlog.debug("💬 Exit intention detected in dictate. Exiting main loop.")
                # self._interaction.unset_eink_idle_mode()
                # self._interaction.wait_for_foreground_display_queue_to_empty()
                # self._interaction.wait_for_busy_foreground_display_to_idle()

        except KeyboardInterrupt:
            self._xlog.info("Pressed Control + C from MainClient")
        except SpeechToTextException as ve:
            self._xlog.error("🛑 SpeechToTextException detected in MainClient run loop: " + str(ve))
        except Exception as e:
            self._xlog.error("🛑 Error in MainClientPTT run loop: " + str(e))
            self._xlog.error(full_stack())  
        
        # # However it happened, just close nicely.
        # self.close_nicely()

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