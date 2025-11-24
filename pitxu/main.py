from multiprocessing import JoinableQueue, shared_memory

from pyxavi import Logger, Config, Dictionary

import logging

from pitxu.lib.gpio.switch_and_led import SwitchAndLed
from pitxu.lib.utils.text import Text
from pitxu.lib.utils.stopwatch import Stopwatch
from pitxu.lib.utils.memory import Memory
from pitxu.lib.utils.xprocess_pool import XprocessPool
from pitxu.lib.chatbot import GeminiChatbot
from pitxu.lib.eink import Display
from pitxu.lib.matrix_led import MatrixLed
from pitxu.lib.speech_to_text import Vosk
from pitxu.lib.text_to_speech import Piper
from pitxu.lib.objects import XprocAction
from definitions import SHARED_EINK_BUSY, SHARED_MATRIX_BUSY, SHARED_MICROPHONE_MUTED, SHARED_SPEAKER_BUSY, SHARED_CHATBOT_BUSY, \
                        PROCESS_EINK, PROCESS_MATRIX, PROCESS_SPEAKER


import sounddevice
import time

class Main:

    _xconfig: Config = None
    _xlog: logging = None

    _display: Display = None
    _matrix: MatrixLed = None
    _chatbot: GeminiChatbot = None
    _dictate: Vosk = None
    _speech: Piper = None
    _switch_and_led: SwitchAndLed = None

    _process_pool: XprocessPool = None

    _manager = None
    _queue_display: JoinableQueue = None
    _queue_matrix: JoinableQueue = None
    _queue_speech: JoinableQueue = None
    _shared_memory: shared_memory.ShareableList = None

    _stopwatch: Stopwatch = None
    _supported_languages: list = []
    _greeting_sentence: str = None
    _goodbye_sentence: str = None
    _exit_words: list = []

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

        # Supported Languages
        self._supported_languages = config.get("languages.supported_languages")

        # Process Pool (initialisation of process handling)
        self._process_pool = XprocessPool(config=self._xconfig, params=self._xparams)

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
        self._process_pool.new_and_start(PROCESS_SPEAKER, target=Piper)

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

        self._xlog.debug("Initialising eInk Display and Macros")
        self._process_pool.new_and_start(PROCESS_EINK, target=Display)

        self._xlog.debug("Initialising Matrix LED Display and Macros")
        self._process_pool.new_and_start(PROCESS_MATRIX, target=MatrixLed)
        # Needs an initial clear
        self._clear_matrix()
    
    def initialize_gpio(self):
        """
        Initialisation of the GPIO switch and LED
        """

        self._xlog.debug("Initialising GPIO Switch and LED")
        self._switch_and_led = SwitchAndLed(config=self._xconfig, params=self._xparams)

    def run(self):

        sw_init = self._stopwatch.start(name="init")

        # Initialise eInk Display and the helper macros
        self._initialize_displays()
        self._show_init_phases(1)

        # Initialise GPIO Switch and LED
        self.initialize_gpio()
        self._show_init_phases(2)

        # Startup splash. It should be understood as a "Loading..." screen.
        self._startup_splash()
        self._show_init_phases(3)
        time.sleep(2)

        # Initialise all classes that require a model. They go per language, that's why it's abstracted
        self._load_models()
        self._show_init_phases(4)

        # Reload all language statics, like the exit words and the greeting / goodbye sentences
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
                self._xlog.debug(">> Greetings")
                sw_greeting = self._stopwatch.start(name="greeting")
                self.communicate(self._greeting_sentence, [self.COMM_TTS, self.COMM_DISPLAY])
                self._xlog.debug("⏱️  Greeting: " + str(self._stopwatch.stop(sw_greeting)))

                question = ""
                dictate_count = 0
                answer_count = 0
                while(not self._text_has_exit_intention(question)):

                    # Check if we pressed the mute switch,
                    # and update the internal state accordingly
                    if self._switch_and_led.update_mute_toggle_state_if_pressed():
                        self._xlog.info("🟢 Mute Toggle pressed.")

                    # Check the switch state
                    # The microphone state is managed via shared memory flags
                    # Therefore, we just need to update the Shared Memory Flag accordingly
                    if self._switch_and_led.is_mute_toggle_on():
                        self.mute_microphone()
                    else:
                        self.unmute_microphone()

                    # Recognize what comes from the microphone
                    sw_dictate = self._stopwatch.continue_or_start(name="dictate" + str(dictate_count))
                    question = self._dictate.recognize()
                    if (question == None or question.strip() == ""):
                        continue
                    self._xlog.debug(">> Recognised dictate")
                    self._xlog.debug("⏱️  Dictate " + str(dictate_count) + ": " + str(self._stopwatch.stop(sw_dictate)))
                    dictate_count += 1

                    # Mute microphone to avoid self-looping, unless the mute switch is on
                    if not self._switch_and_led.is_mute_switch_on():
                        self.mute_microphone()
                        self._xlog.debug("🔇 Muting the microphone. Now is [" + str(self._process_pool.get_memory_manager().read_shared_memory_flag(SHARED_MICROPHONE_MUTED)) + "]")

                    # Avoid calling the Chatbot when exiting
                    if self._text_has_exit_intention(question):
                        # Just assume a goodbye
                        answer = self._goodbye_sentence
                    else:
                        # Here we start with the Chatbot.
                        # We set it as busy in shared memory, so the Matrix can show the thinking effect
                        self.set_chatbot_busy()
                        self._show_thinking()
                        answer = self._chatbot.ask(question)
                        self.unset_chatbot_busy()
                        self._process_pool.get_memory_manager().wait_for_busy_process_to_idle(SHARED_MATRIX_BUSY)
                    
                    # Clean the answer first, just in case
                    answer = Text.remove_emojis(answer)
                    answer = Text.remove_markdown(answer)
                    answer = Text.replace_known_text(answer, self._xconfig.get("language.text_replacements." + self._xparams.get("language"), {}))

                    # Answer
                    sw_answer = self._stopwatch.start(name="answer" + str(answer_count))
                    self.communicate(answer, [self.COMM_TTS, self.COMM_DISPLAY])
                    self._xlog.debug("⏱️  Answer " + str(answer_count) + ": " + str(self._stopwatch.stop(sw_answer)))
                    answer_count += 1

                    # Unmute microphone to continue listening, unless the mute switch is on
                    if not self._switch_and_led.is_mute_switch_on():
                        self.unmute_microphone()
                        self._xlog.debug("🔊 Unmuting the microphone. Now is [" + str(self._process_pool.get_memory_manager().read_shared_memory_flag(SHARED_MICROPHONE_MUTED)) + "]")

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
        self._process_pool.wait_for_queue_to_empty(PROCESS_EINK)
        self._process_pool.wait_for_queue_to_empty(PROCESS_SPEAKER)
        # Yeah, but still there is job to be done (speaking, for example)
        self._process_pool._shared_memory.wait_for_busy_process_to_idle(SHARED_EINK_BUSY)
        self._process_pool._shared_memory.wait_for_busy_process_to_idle(SHARED_SPEAKER_BUSY)

    def _text_has_exit_intention(self, text):
        return text in self._exit_words
    
    def close_nicely(self):
        sw_closing = self._stopwatch.continue_or_start(name="closing")
        self._xlog.debug("Closing nicely...")

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
        self._xlog.info("💡  Memory used:" + str(Memory.use(Memory.MEGABYTES)) + " MB")
    
    def clear_displays(self):
        self._xlog.debug("Clearing the eInk.")
        self._clear_display()
        self._xlog.debug("Clearing the LED Matrix.")
        self._clear_matrix()

    # ------- Communication with Queues ---------
    
    def _say(self, message: str):
        self._process_pool.send(PROCESS_SPEAKER, XprocAction.SAY, message)
        self._process_pool.send(PROCESS_MATRIX, XprocAction.SAY, message)
    
    def _show(self, message: str):
        self._process_pool.send(PROCESS_EINK, XprocAction.SHOW, message)
        # self._process_pool.send(PROCESS_MATRIX, XprocAction.LED, message)
    
    def _startup_splash(self):
        self._process_pool.send(PROCESS_EINK, XprocAction.STARTUP)
        self._process_pool.wait_for_queue_to_empty(PROCESS_EINK)
    
    def _show_init_phases(self, step: int):
        self._process_pool.send(PROCESS_MATRIX, XprocAction.INIT_STEP, str(step))
    
    def _show_thinking(self):
        self._process_pool.send(PROCESS_MATRIX, XprocAction.THINKING)
    
    def _clear_display(self):
        # Now that we use partial refresh, the clear needs a previous white rectangle.
        # First a soft clear, so the screen is white
        self._process_pool.send(PROCESS_EINK, XprocAction.SOFT_CLEAR)
        # Full clear, to ensure a reset.
        self._process_pool.send(PROCESS_EINK, XprocAction.CLEAR)

    def _clear_matrix(self):
        self._process_pool.send(PROCESS_MATRIX, XprocAction.LED_CLEAR)
    
    # ------- Communication with Flags ---------
    
    def mute_microphone(self):
        self._process_pool.get_memory_manager().write_shared_memory_flag(SHARED_MICROPHONE_MUTED, True)
    
    def unmute_microphone(self):
        self._process_pool.get_memory_manager().write_shared_memory_flag(SHARED_MICROPHONE_MUTED, False)
    
    def set_chatbot_busy(self):
        self._process_pool.get_memory_manager().write_shared_memory_flag(SHARED_CHATBOT_BUSY, True)
        self._xlog.debug("🤖 Setting Chatbot as busy.")
    
    def unset_chatbot_busy(self):
        self._process_pool.get_memory_manager().write_shared_memory_flag(SHARED_CHATBOT_BUSY, False)
        self._xlog.debug("🤖 Unsetting Chatbot as busy.")