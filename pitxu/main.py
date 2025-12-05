from multiprocessing import JoinableQueue, shared_memory
from subprocess import call

from pyxavi import Logger, Config, Dictionary, Storage

import logging
from functools import partial

from pitxu.lib.utils.text import Text
from pitxu.lib.utils.stopwatch import Stopwatch
from pitxu.lib.utils.memory import Memory
from pitxu.lib.utils.xprocess_pool import XprocessPool
from pitxu.lib.utils.maintenance import Maintenance
from pitxu.lib.utils.reminders import Reminders
from pitxu.lib.chatbot import GeminiChatbot
from pitxu.lib.eink import Display, EinkCanvas
from pitxu.lib.matrix_led import MatrixLed
from pitxu.lib.speech_to_text import Vosk
from pitxu.lib.text_to_speech import Piper
from pitxu.lib.objects import XprocAction, ChatbotResponse, FunctionCallPair
from definitions import SHARED_EINK_BUSY, SHARED_MATRIX_BUSY, SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY, \
                        SHARED_CHATBOT_BUSY, SHARED_EINK_IDLE_MODE, SHARED_CHATBOT_ANSWER_IS_ERROR, \
                        QUEUE_EINK, QUEUE_MATRIX, QUEUE_SPEAKER


import sounddevice
import time
from datetime import datetime

class Main:

    _xconfig: Config = None
    _xlog: logging = None
    _state: Storage = None
    _last_processed_minute: int = -1

    _chatbot: GeminiChatbot = None
    _dictate: Vosk = None

    _process_pool: XprocessPool = None

    _manager = None
    _queue_display: JoinableQueue = None
    _queue_matrix: JoinableQueue = None
    _queue_speech: JoinableQueue = None
    _shared_memory: shared_memory.ShareableList = None

    _chatbot_client_callbacks: dict[str, callable] = None

    _maintenance: Maintenance = None
    _reminders: Reminders = None

    _stopwatch: Stopwatch = None
    _supported_languages: list = []
    _greeting_sentence: str = None
    _goodbye_sentence: str = None
    _exit_words: list = []
    _tokens_counter: int = 0

    COMM_DISPLAY = "display"
    COMM_MATRIX = "matrix"
    COMM_TTS = "tts"

    ENGLISH: str = "en-us"
    CATALAN: str = "ca"
    GERMAN: str = "de"
    SPANISH: str = "es"

    # Shared memory flag positions
    SHARED_SPEAKER_BUSY = 0
    SHARED_EINK_BUSY = 1
    SHARED_MATRIX_BUSY = 2

    def __init__(self, config: Config = None, params: Dictionary = None):

        # Possible runtime parameters
        self._xparams = params

        # Config is mandatory
        if config is None:
            raise RuntimeError("Config can not be None")
        self._xconfig = config

        # Common Logger
        self._xlog = Logger(config=config, base_path=params.get("base_path", "")).get_logger()
        self._xparams.set("logger", self._xlog)

        # Initial Language
        self._xparams.set("language", config.get("app.default_language", self.CATALAN))

        # Initialize State
        self._state = Storage(filename=self._xconfig.get("storage.path") + self._xconfig.get("storage.state_file"))

        # Initialize Maintenance utility
        self._maintenance = Maintenance(config=self._xconfig, params=self._xparams)

        # Supported Languages
        self._supported_languages = config.get("languages.supported_languages")

        # Process Pool (initialisation of process handling)
        self._process_pool = XprocessPool(config=self._xconfig, params=self._xparams)

        # The Reminders functionality
        self._reminders = Reminders(config=self._xconfig, params=self._xparams)

        # Stopwatch to measure times
        self._stopwatch = Stopwatch()

    def load_language(self, new_language: str):
        # Ensure that the language is supported
        if new_language not in self._supported_languages:
            raise RuntimeError("Language [" + new_language + "] is not supported")
        
        # Define the language to use
        self._xparams.set("language", new_language)

        # Reload the models now that we have a new language defined
        self._load_models()

        # Reload all language statics, like the exit words and the greeting / goodbye sentences
        self._load_language_statics()

    def _load_models(self):
        
        # Initialise Speech-to-Text. This runs in the main process
        self._xlog.debug("Initialising the Speech-to-Text with language [" + self._xparams.get("language") + "]")
        self._dictate = Vosk(config=self._xconfig, params=self._xparams)

        # Initialise Text-To-Speech.
        self._xlog.debug("Initialising the Text-to-Speech with language [" + self._xparams.get("language") + "]")
        self._process_pool.new_and_start(QUEUE_SPEAKER, target=Piper)

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

        # Compile exit words
        all_possible_exit_words = []
        for language, exit_words in dict(self._xconfig.get("language.exit_words")).items():
            for word in exit_words:
                if word not in all_possible_exit_words:
                    all_possible_exit_words .append(word)
        self._xlog.debug("Load ALL possible exit words " + str(all_possible_exit_words) + "")
        self._exit_words = all_possible_exit_words
    
    def _initialize_displays(self):
        """
        Initialisation of the displays and macros
        """

        self._xlog.info("Initialising eInk Display and Macros")
        self._process_pool.new_and_start(QUEUE_EINK, target=Display)

        self._xlog.info("Initialising Matrix LED Display and Macros")
        self._process_pool.new_and_start(QUEUE_MATRIX, target=MatrixLed)
        # Needs an initial clear
        self._clear_matrix()

    async def run(self):

        sw_init = self._stopwatch.start(name="init")

        # Execute the initial maintenance tasks
        self._maintenance.clean_previous_mocked_images()

        # Initialise Displays and the helper macros.
        self._initialize_displays()
        self._show_init_phases(1)

        # Startup splash. It should be understood as a "Loading..." screen.
        self._startup_splash()
        self._show_init_phases(2)
        time.sleep(2)

        # At this point, we better wait for all queues to be empty.
        # This basically involves eInk (for the splash).
        # Matrix would also be related, but as we're showing the init phases, it's not that critical.
        self._process_pool.wait_for_queue_to_empty(QUEUE_EINK)
        self._show_init_phases(3)

        # Initialise all classes that require a model. They go per language.
        self._load_models()
        self._show_init_phases(4)

        # Load all language statics, like the exit words and the greeting / goodbye sentences
        self._load_language_statics()
        self._show_init_phases(5)

        self._xlog.debug("⏱️  Initialisations: " + str(self._stopwatch.stop(sw_init)))

        try:
            # Read from microphone
            # Correct format for Vosk is PCM 16khz 16bit mono
            with sounddevice.RawInputStream(samplerate=self._dictate.samplerate,
                                blocksize = 0, 
                                device=self._dictate.device,
                                dtype="int16", 
                                channels=1,
                                callback=self._dictate.callback) as input_stream:
                self._show_init_phases(6)
                
                # Welcome greeting
                self._xlog.debug("Say Greetings")
                sw_greeting = self._stopwatch.start(name="greeting")
                # With the new function call reactions, we maybe don't want anymore to show the text in the screen anymore
                # self.communicate(self._greeting_sentence, [self.COMM_TTS, self.COMM_DISPLAY])
                self._show_idle()
                self.communicate(self._greeting_sentence, [self.COMM_TTS])

                self._xlog.debug("⏱️  Greeting: " + str(self._stopwatch.stop(sw_greeting)))
                self._show_init_phases(7)

                # Set up of all the session context we need for the Chatbot and the MCP tools
                async with self._chatbot.get_session_manager() as chatbot_session_manager:
                    self._show_init_phases(8)

                    # Initialise the Chatbot async context with all the tools from the session manager
                    await self._chatbot.initialize_async(tools=chatbot_session_manager.tools)
                    self._chatbot_client_callbacks = self._chatbot.get_session_manager().get_client_callbacks_by_function_name()
                    self._show_init_phases(9)

                    question = ""
                    dictate_count = 0
                    answer_count = 0
                    while(not self._text_has_exit_intention(question)):

                        # Check the things to do every minute
                        # This includes reminders checking and speaking them out.
                        self.do_every_minute_tasks()

                        # Show idle screen in eInk if not already showing it
                        if not self.is_eink_in_idle_mode():
                            self._show_idle()

                        # Recognize what comes from the microphone
                        sw_dictate = self._stopwatch.continue_or_start(name="dictate" + str(dictate_count))
                        question = self._dictate.recognize()
                        if (question == None or question.strip() == ""):
                            # Nothing recognized, nothing to process.
                            continue

                        # Still here? Then something got recognised.
                        self._xlog.debug("💬 Recognised dictate")
                        self._xlog.debug("⏱️  Dictate " + str(dictate_count) + ": " + str(self._stopwatch.stop(sw_dictate)))
                        dictate_count += 1

                        # Mute microphone to avoid self-looping
                        self.mute_microphone()

                        # To keep track of the communication channels to ignore
                        # Because the outcome of any chatbot's function call may be using them.
                        comm_channels_to_ignore = []

                        # Avoid calling the Chatbot when we can exit directly.
                        if self._text_has_exit_intention(question):
                            # Just assume a goodbye
                            answer = self._goodbye_sentence
                        else:
                            # Here we start with the Chatbot.
                            # We set it as busy in shared memory, so the Matrix can show the thinking effect
                            self.set_chatbot_busy()
                            self._show_thinking()
                            chat_response: ChatbotResponse = await self._chatbot.ask_async(question)
                            self._tokens_counter += chat_response.metadata.total_token_count if chat_response.metadata and chat_response.metadata.total_token_count is not None else 0
                            answer = chat_response.text
                            try:
                                self._xlog.debug("Function calls in the chat history: " + ", ".join(chat_response.function_call_history.get_names()))
                                if chat_response.function_call_history.get_last().has_response():
                                    self._xlog.debug("🗣️ Received function call response. Reacting.")
                                    # Shutdown and Reboot interrupt the flow and directly shutdown,
                                    # calling `close_nicely()` from there.
                                    # Keep in mind that here we may have played with BUSY flags.
                                    comm_channels_to_ignore.extend(self.react_on_last_function_call(chat_response.function_call_history.get_last()))
                                    # TODO: Feels like sometimes the flow does not come back here. Apparenty, the second time asking for the hour.
                            except Exception as e:
                                self._xlog.error("🛑 Error reacting to function call: " + str(e))
                            self.unset_chatbot_busy()
                            self._process_pool.get_memory_manager().wait_for_busy_process_to_idle(SHARED_MATRIX_BUSY)
                        
                        # Do we actully have any answer?
                        if answer is None or answer.strip() == "":
                            self._xlog.debug(">> Empty answer from Chatbot, we should not be here, it should be handled inside Chatbot.")
                            answer = "ERROR"
                        
                        # Clean the answer first, just in case
                        answer = Text.remove_emojis(answer)
                        answer = Text.remove_markdown(answer)
                        answer = Text.replace_known_text(answer, self._xconfig.get("language.text_replacements." + self._xparams.get("language"), {}))

                        # Answer
                        sw_answer = self._stopwatch.start(name="answer" + str(answer_count))
                        # With the new function call reactions, we maybe don't want anymore to show the text in the screen anymore
                        #self.communicate(answer, list(set([self.COMM_TTS, self.COMM_DISPLAY]) - set(comm_channels_to_ignore)))
                        self.communicate(answer, list(set([self.COMM_TTS]) - set(comm_channels_to_ignore)))
                        self._xlog.debug("⏱️  Answer " + str(answer_count) + ": " + str(self._stopwatch.stop(sw_answer)))
                        answer_count += 1

                        # If we were communicating an error, it's over and start new
                        if self.is_chatbot_error():
                            self.unset_chatbot_error()

                        # Unmute microphone to continue listening
                        self.unmute_microphone()
                    
                    # We arrived here because the user wanted to exit the main loop
                    # Make sure we leave the state properly
                    self._xlog.debug("💬 Exit intention detected in dictate. Exiting main loop.")
                    self.unset_eink_idle_mode()
                    self._process_pool.wait_for_queue_to_empty(QUEUE_EINK)
                    self._process_pool._shared_memory.wait_for_busy_process_to_idle(SHARED_EINK_BUSY)   

        except KeyboardInterrupt:
            self._xlog.info("Pressed Control + C from main")
        
        # However it happened, just close nicely.
        self.close_nicely()
    
    def communicate(self, text: str, channels: list):
        """
        Communicates to the user using the channels defined.

        It is an abstraction to deliver in one shot display and audio (and whatever else in the future).
        It is a NOT blocking process, runs every channel in a separate process so they can run in parallel,
        speeding up the overall run.
        """

        # In case we want TTS, we need to pause the mic
        # this is done within the TTS process via a shared memory flag that tells the STT to pause

        if self.COMM_TTS in channels:
            # Say the answer
            self._xlog.debug("Say Communication")
            # We already have the TTS in a Process, listening for elements in the queue
            self._say(text)

        if self.COMM_DISPLAY in channels:
            # Show the answer
            self._xlog.debug("Show Communication")
            self._show(text)
        
        # We want that the main thread waits until some of the actions finished in the subprocesses
        # still there is job to be done (speaking, for example)
        if self.COMM_DISPLAY in channels:
            self._process_pool.wait_for_queue_to_empty(QUEUE_EINK)
            self._process_pool._shared_memory.wait_for_busy_process_to_idle(SHARED_EINK_BUSY)
        
        if self.COMM_TTS in channels:
            self._process_pool.wait_for_queue_to_empty(QUEUE_SPEAKER)
            self._process_pool._shared_memory.wait_for_busy_process_to_idle(SHARED_SPEAKER_BUSY)
            # Speaking often involves Matrix too (for the speaking effect)
            self._process_pool.wait_for_queue_to_empty(QUEUE_MATRIX)
            self._process_pool._shared_memory.wait_for_busy_process_to_idle(SHARED_MATRIX_BUSY)
    
    def react_on_last_function_call(self, function_call_pair: FunctionCallPair) -> list[str]:
        """
        Reacts to the last function call beyond simply answering, like expressions, emotions, or actions.

        Args:
            function_call (FunctionCallPair): The last function call pair from the chatbot.
        
        Returns:
            list[str]: List of communications channels that should be ignored in the communication() method.
        """

        # The idea here is to be able to use the hardware as part of the response, like moving eyes,
        #   or showing the hour in the eInk if asked for the time...
        #
        # More importantly, this is the way to perform a proper close_nicely(), besides just
        #   shutting down or rebooting the system without caring.
        # For this last point to happen, we need to control the answer of the tool, give something
        #   specific to search for here.

        try:

            communication_channels_to_ignore: list[str] = []
            if function_call_pair.has_response():
                self._xlog.debug("⚡️ Reacting to function call: " + str(function_call_pair.function_name))
                # Here we can parse the function response and act accordingly
                # For example, if the function call is to get the current time, we can display it on an eInk screen
                if function_call_pair.function_name in self._chatbot_client_callbacks.keys():
                    # Generic callback execution for other functions that have a defined callback

                    value = function_call_pair.function_response.response.get("result", "unknown")
                    args = function_call_pair.function_call.arguments
                    self._xlog.debug("📺 Show the function response in the eInk: " + str(value))
                    self.unset_eink_idle_mode()
                    self._process_pool.wait_for_queue_to_empty(QUEUE_EINK)
                    self._process_pool._shared_memory.wait_for_busy_process_to_idle(SHARED_EINK_BUSY)

                    # Here we call the callback from within the command, passing the context of `main` and the value
                    # Whatever happens, it's done there inside.
                    partial(
                        self._chatbot_client_callbacks[function_call_pair.function_name],
                        self,
                        value,
                        args
                    )()

                    communication_channels_to_ignore.append(self.COMM_DISPLAY)
                
                elif function_call_pair.function_name == "error":
                    self._xlog.debug("🚨  Showing the ERROR in the eInk")

                    self.unset_eink_idle_mode()
                    self._process_pool.wait_for_queue_to_empty(QUEUE_EINK)
                    self._process_pool._shared_memory.wait_for_busy_process_to_idle(SHARED_EINK_BUSY)

                    self.show_arbitrary_text_on_eink(
                        icon="🚨",
                        text=function_call_pair.function_response.response.get("result", "unknown"),
                        font_size=EinkCanvas.FONT_BIG_SIZE)

                    communication_channels_to_ignore.append(self.COMM_DISPLAY)

                elif function_call_pair.function_name == "shutdown_local_machine":
                    self._xlog.debug("💤 Preparing for shutdown...")
                    # Unset eInk idle mode to be able to show stuff if needed
                    self.unset_eink_idle_mode()
                    self._process_pool.wait_for_queue_to_empty(QUEUE_EINK)
                    self._process_pool._shared_memory.wait_for_busy_process_to_idle(SHARED_EINK_BUSY)
                    # The chatbot is in "Thinking" mode, we need to unset it
                    self.unset_chatbot_busy()
                    # And also reactivate the microphone because it keeps the state on shutdowns / reboots
                    self.unmute_microphone()
                    # Now wait until busy processes are done
                    self._process_pool.get_memory_manager().wait_for_all_busy_process_to_idle()
                    # Finally, close nicely and shutdown
                    self.close_nicely()
                    try:
                        call("sudo nohup shutdown -h now", shell=True)
                    except Exception as e:
                        self._xlog.error(f"Error during shutdown: {e}")
                elif function_call_pair.function_name == "reboot_local_machine":
                    self._xlog.debug("♻️  Preparing for reboot...")
                    # Unset eInk idle mode to be able to show stuff if needed
                    self.unset_eink_idle_mode()
                    self._process_pool.wait_for_queue_to_empty(QUEUE_EINK)
                    self._process_pool._shared_memory.wait_for_busy_process_to_idle(SHARED_EINK_BUSY)
                    # The chatbot is in "Thinking" mode, we need to unset it
                    self.unset_chatbot_busy()
                    # And also reactivate the microphone because it keeps the state on shutdowns / reboots
                    self.unmute_microphone()
                    # Now wait until busy processes are done
                    self._process_pool.get_memory_manager().wait_for_all_busy_process_to_idle()
                    # Finally, close nicely and shutdown
                    self.close_nicely()
                    try:
                        call("sudo nohup reboot", shell=True)
                    except Exception as e:
                        self._xlog.error(f"Error during reboot: {e}")

            # Finally we return the communication channels to ignore
            # Because we're actually using them here.
            return communication_channels_to_ignore
        except Exception as e:
            self._xlog.error("🛑 Error reacting to function call: " + str(e))

    def _text_has_exit_intention(self, text):
        return text in self._exit_words
    
    def close_nicely(self):
        sw_closing = self._stopwatch.continue_or_start(name="closing")
        self._xlog.debug("Closing nicely...")

        # Persist state
        self.persist_state()

        # Stop eInk idle mode if active
        self.unset_eink_idle_mode()
        self._process_pool.wait_for_queue_to_empty(QUEUE_EINK)

        # Clean the displays
        self.clear_displays()

        # Wait for all the queues and processes to get empty
        self._process_pool.wait_for_all_queues_to_empty()
        self._process_pool._shared_memory.wait_for_all_busy_process_to_idle()

        # Finish all related multiprocess stuff
        self._process_pool.finish_leftover_processes()

        # ------ Final logs ------

        self._xlog.debug("We should be now nicely closed")
        self._xlog.debug("⏱️  Closed: " + str(self._stopwatch.stop(sw_closing)))

        # Here comes anything that we want to do before leaving
        self._xlog.info("⏱️  Final Stopwatch report:\n" + self._stopwatch.stop_and_report())
        self._xlog.info("💡  Memory used: " + str(Memory.use(Memory.MEGABYTES)) + " MB")
        self._xlog.info("💰  Tokens used: " + str(self._tokens_counter))
    
    def persist_state(self):

        self._state.set("tokens_counter", int(self._state.get("tokens_counter", 0)) + self._tokens_counter)
        self._state.write_file()
        self._xlog.debug("Persisted state to " + self._xconfig.get("storage.state_file"))

    def clear_displays(self):
        self._xlog.debug("Clearing the eInk.")
        self._clear_display()
        self._xlog.debug("Clearing the LED Matrix.")
        self._clear_matrix()

    # ------- Communication with Queues ---------
    
    def _say(self, message: str):
        self._process_pool.send(QUEUE_SPEAKER, XprocAction.SAY, message)
        self._process_pool.send(QUEUE_MATRIX, XprocAction.SAY, message)
    
    def _show(self, message: str):
        self._process_pool.send(QUEUE_EINK, XprocAction.SHOW, message)
    
    def _startup_splash(self):
        self._process_pool.send(QUEUE_EINK, XprocAction.STARTUP)
    
    def _show_init_phases(self, step: int):
        self._process_pool.send(QUEUE_MATRIX, XprocAction.INIT_STEP, str(step))
    
    def _show_thinking(self):
        self._process_pool.send(QUEUE_MATRIX, XprocAction.THINKING)

    def _show_idle(self):
        self._xlog.debug("👀 Starting eInk idle mode from Main")
        self.set_eink_idle_mode()
        self._process_pool.send(QUEUE_EINK, XprocAction.SHOW_IDLE_EINK)

    def _clear_display(self):
        # Now that we use partial refresh, the clear needs a previous white rectangle.
        # First a soft clear, so the screen is white
        self._process_pool.send(QUEUE_EINK, XprocAction.SOFT_CLEAR)
        # Full clear, to ensure a reset.
        self._process_pool.send(QUEUE_EINK, XprocAction.CLEAR)

    def _clear_matrix(self):
        self._process_pool.send(QUEUE_MATRIX, XprocAction.LED_CLEAR)

    # ------- Communication with Queues, by Command's Callbacks ---------

    def get_eInk_display(self) -> Display:
        return self._process_pool.get_process(QUEUE_EINK)
    
    def show_arbitrary_text_on_eink(
            self,
            icon: str = None,
            text: str = None,
            font_size: int = 24,
            header: str = None,
            font_header_size: int = 32,
            padding = 5
        ):
        self._process_pool.send(QUEUE_EINK, XprocAction.SHOW_ARBITRARY_TEXT_EINK, {
            "icon": icon,
            "text": text,
            "font_size": font_size,
            "header": header,
            "font_header_size": font_header_size,
            "padding": padding
        })

    def show_arbitrary_text_on_eink_while_speaking(
            self,
            icon: str = None,
            text: str = None,
            font_size: int = 24,
            header: str = None,
            font_header_size: int = 32,
            padding = 5
        ):
        self._process_pool.send(QUEUE_EINK, XprocAction.SHOW_TALKING_ARBITRARY_EINK, {
            "icon": icon,
            "text": text,
            "font_size": font_size,
            "header": header,
            "font_header_size": font_header_size,
            "padding": padding
        })

    def show_image_on_eink(self, image: dict):
        self._process_pool.send(QUEUE_EINK, XprocAction.SHOW_IMAGE_EINK, image)

    def show_image_on_led(self, image: str):
        self._process_pool.send(QUEUE_MATRIX, XprocAction.SHOW_IMAGE_LED, image)

    # ------- Communication with Flags ---------
    
    def mute_microphone(self):
        self._process_pool.get_memory_manager().write_shared_memory_flag(SHARED_MICROPHONE_MUTED, True)
        self._xlog.debug("🔇 Muting the microphone. Now is [" + str(self._process_pool.get_memory_manager().read_shared_memory_flag(SHARED_MICROPHONE_MUTED)) + "]")
    
    def unmute_microphone(self):
        self._process_pool.get_memory_manager().write_shared_memory_flag(SHARED_MICROPHONE_MUTED, False)
        self._xlog.debug("🔊 Unmuting the microphone. Now is [" + str(self._process_pool.get_memory_manager().read_shared_memory_flag(SHARED_MICROPHONE_MUTED)) + "]")
    
    def set_chatbot_busy(self):
        self._process_pool.get_memory_manager().write_shared_memory_flag(SHARED_CHATBOT_BUSY, True)
        self._xlog.debug("🤖 Setting Chatbot as busy.")
    
    def unset_chatbot_busy(self):
        self._process_pool.get_memory_manager().write_shared_memory_flag(SHARED_CHATBOT_BUSY, False)
        self._xlog.debug("🤖 Unsetting Chatbot as busy.")
    
    def is_chatbot_error(self) -> bool:
        return self._process_pool.get_memory_manager().read_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR)
    
    def unset_chatbot_error(self):
        self._process_pool.get_memory_manager().write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, False)
    
    def is_eink_in_idle_mode(self) -> bool:
        return self._process_pool.get_memory_manager().read_shared_memory_flag(SHARED_EINK_IDLE_MODE)
    
    def set_eink_idle_mode(self):
        self._process_pool.get_memory_manager().write_shared_memory_flag(SHARED_EINK_IDLE_MODE, True)

    def unset_eink_idle_mode(self):
        self._process_pool.get_memory_manager().write_shared_memory_flag(SHARED_EINK_IDLE_MODE, False)
    
    # ------- Stuff to do every minute -------

    def do_every_minute_tasks(self):
        current_minute = time.localtime().tm_min
        if current_minute != self._last_processed_minute:
            self._last_processed_minute = current_minute
            self._xlog.debug("🕐 New minute detected: " + str(current_minute) + ". Running every-minute tasks.")
            # Get the possible reminder for the current date and time
            date_str = datetime.now().strftime(Reminders.FORMAT_DATE)
            time_str = datetime.now().strftime(Reminders.FORMAT_TIME)
            reminder: dict = self._reminders.get_reminder(date_str, time_str)
            if reminder is not False:
                self._xlog.debug("📝 Reminder found for now: " + str(reminder))
                # Show reminder in eInk and say it
                reminder_text_for_speaking = self._xconfig.get("language.reminders.reminder_announcement." + self._xparams.get("language")) % reminder.get("text", "")
                self.unset_eink_idle_mode()
                self._process_pool.wait_for_queue_to_empty(QUEUE_EINK)
                self._process_pool._shared_memory.wait_for_busy_process_to_idle(SHARED_EINK_BUSY)
                self.show_arbitrary_text_on_eink(
                    icon="📝",
                    text=reminder.get("text", ""),
                    font_size=EinkCanvas.FONT_BIG_SIZE)
                self.mute_microphone()
                self.communicate(reminder_text_for_speaking, [self.COMM_TTS])
                self.unmute_microphone()
                # Remove the reminder now that it's been announced
                self._reminders.delete_reminder(date_str, time_str)