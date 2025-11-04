from multiprocessing import set_start_method, Process, Queue, Manager, shared_memory

from pyxavi import Logger, Config, Dictionary

import logging

from pitxu.lib.utils import Text, Stopwatch, Memory
from pitxu.lib.chatbot import GeminiChatbot
from pitxu.lib.eink import EinkDisplay, Macros
from pitxu.lib.speech_to_text import Vosk
from pitxu.lib.text_to_speech import PiperMultiprocess
from pitxu.lib.dto import QueueItemType, QueueItemAction


import sounddevice
import time

SHARED_MEMORY_NAME = "pitxu_shared_memory"

class Main:

    _config: Config = None
    _logger: logging = None

    _display: EinkDisplay = None
    _macros: Macros = None
    _chatbot: GeminiChatbot = None
    _dictate: Vosk = None
    _speech: PiperMultiprocess = None

    _manager = None
    _queue: Queue = None
    _shared_memory: shared_memory.ShareableList = None

    _stopwatch: Stopwatch = None
    _supported_languages: list = []
    _greeting_sentence: str = None
    _goodbye_sentence: str = None
    _exit_words: list = []

    COMM_DISPLAY = "display"
    COMM_TTS = "tts"

    ENGLISH: str = "en-us"
    CATALAN: str = "ca"
    GERMAN: str = "de"
    SPANISH: str = "es"

    def __init__(self, config: Config = None, params: Dictionary = None):

        # Possible runtime parameters
        self._parameters = params

        # Config is mandatory
        if config is None:
            raise RuntimeError("Config can not be None")
        self._config = config

        # Common Logger
        self._logger = Logger(config=config, base_path=params.get("base_path", "")).get_logger()
        self._parameters.set("logger", self._logger)

        # Initial Language
        self._parameters.set("language", config.get("app.default_language", self.CATALAN))

        # Supported Languages
        self._supported_languages = config.get("languages.supported_languages")

        # Initialisating Shared Memory to handle execution flags between processes
        self._parameters.set("shared_memory_name", SHARED_MEMORY_NAME)
        self._shared_memory = shared_memory.ShareableList([
            False  # pause_mic
        ], name=SHARED_MEMORY_NAME)
        if self._shared_memory is None:
            self._logger.error("Shared Memory is None, cannot write 'pause_mic' flag")

        self._stopwatch = Stopwatch()

    def load_language(self, new_language: str):
        # Ensure that the language is supported
        if new_language not in self._supported_languages:
            raise RuntimeError("Language [" + new_language + "] is not supported")
        
        # Define the language to use
        self._parameters.set("language", new_language)

        # Reload the models now that we have a new language defined
        self.load_models()

        # Reload all language statics, like the exit words and the greeting / goodbye sentences
        self.load_language_statics()

    def load_models(self):

        # Some of the models will be hold in separate processes
        # Communication with them is done via a Queue
        self._manager = Manager()
        self._queue = self._manager.Queue()

        # The `forkserver` method is the only one that allows to initialze the SoundDevice in the child thread
        # without issues. The `spawn` method fails when initializing the OutputStream, and `fork` is not
        # available in Mac.
        set_start_method('forkserver', force=True)  # For Mac M1/M2 compatibility
        
        # Initialise Speech-to-Text
        self._logger.debug("Initialising the Speech-to-Text with language [" + self._parameters.get("language") + "]")
        self._dictate = Vosk(self._config, params=self._parameters)

        # Initialise Text-To-Speech. Please note that the object is a child of Process,
        #   so it only communicate with it via the queue.
        self._logger.debug("Initialising the Text-to-Speech with language [" + self._parameters.get("language") + "]")
        # self._speech = Piper(self._config, params=self._parameters)
        self._speech = PiperMultiprocess(self._config, params=self._parameters, queue=self._queue)
        self._speech.start()
        self._queue.put((QueueItemType.ACTION, QueueItemAction.INITIALIZE))

        # Initialise Chatbot
        self._logger.debug("Initialising the Chatbot Client with language [" + self._parameters.get("language") + "]")
        self._chatbot = GeminiChatbot(config=self._config, params=self._parameters)
    
    def load_language_statics(self):

        # Load the greeting sentence
        self._logger.debug("Load Greeting with language [" + self._parameters.get("language") + "]")
        self._greeting_sentence = self._config.get("language.greeting." + self._parameters.get("language"))

        # Load the goodbye sentence
        self._logger.debug("Load Goodbye with language [" + self._parameters.get("language") + "]")
        self._goodbye_sentence = self._config.get("language.goodbye." + self._parameters.get("language"))

        # Compile exit words
        all_possible_exit_words = []
        for language, exit_words in dict(self._config.get("language.exit_words")).items():
            for word in exit_words:
                if word not in all_possible_exit_words:
                    all_possible_exit_words .append(word)
        self._logger.debug("Load ALL possible exit words " + str(all_possible_exit_words) + "")
        self._exit_words = all_possible_exit_words
    
    def run(self):

        sw_init = self._stopwatch.start(name="init")

        # Initialise eInk Display and the helper macros
        self._logger.debug("Initialising the e-Ink")
        self._display = EinkDisplay(config=self._config, params=self._parameters)
        self._macros = Macros(self._config, params=self._parameters)

        # Startup splash. It should be understood as a "Loading..." screen.
        self._macros.startup_splash(self._display)
        time.sleep(2)

        # Initialise all classes that require a model. They go per language, that's why it's abstracted
        self.load_models()

        # Reload all language statics, like the exit words and the greeting / goodbye sentences
        self.load_language_statics()

        self._logger.debug("⏱️  Initialisations: " + str(self._stopwatch.stop(sw_init)))

        try:
            # Read from microphone
            # Correct format for Vosk is PCM 16khz 16bit mono
            with sounddevice.RawInputStream(samplerate=self._dictate.samplerate,
                                blocksize = 0, 
                                device=self._dictate.device,
                                dtype="int16", 
                                channels=1,
                                callback=self._dictate.callback) as input_stream:
                
                # Welcome greeting
                self._logger.debug(">> Greetings")
                sw_greeting = self._stopwatch.start(name="greeting")
                self.communicate(self._greeting_sentence,
                                 [self.COMM_TTS, self.COMM_DISPLAY],
                                 input_stream)
                self._logger.debug("⏱️  Greeting: " + str(self._stopwatch.stop(sw_greeting)))

                question = ""
                dictate_count = 0
                answer_count = 0
                while(not self._text_has_exit_intention(question)):
                    try:
                        # Recognize what comes from the microphone
                        sw_dictate = self._stopwatch.continue_or_start(name="dictate" + str(dictate_count))
                        question = self._dictate.recognize()
                        if (question == None or question.strip() == ""):
                            continue
                        self._logger.debug(">> Recognised dictate")
                        self._logger.debug("⏱️  Dictate " + str(dictate_count) + ": " + str(self._stopwatch.stop(sw_dictate)))
                        dictate_count += 1

                        # Avoid calling the Chatbot when exiting
                        if self._text_has_exit_intention(question):
                            # Just assume a goodbye
                            answer = self._goodbye_sentence
                        else:
                            # Here we start with the Chatbot
                            answer = self._chatbot.ask(question)
                        
                        # Clean the answer first, just in case
                        answer = Text.remove_emojis(answer)

                        # Answer
                        sw_answer = self._stopwatch.start(name="answer" + str(answer_count))
                        self.communicate(answer, [self.COMM_TTS, self.COMM_DISPLAY], input_stream)
                        self._logger.debug("⏱️  Answer " + str(answer_count) + ": " + str(self._stopwatch.stop(sw_answer)))
                        answer_count += 1
                    except KeyboardInterrupt:
                        break
                
                # We're here if the user said the exit words
                self.close_nicely()

        except KeyboardInterrupt:
            self._logger.info("Pressed Control + C from main")
            self.close_nicely()
        
        # Here comes anything that we want to do before leaving
        self._logger.info("⏱️  Final Stopwatch report:\n" + self._stopwatch.stop_and_report())
        self._logger.info("💡  Memory used:" + str(Memory.use(Memory.MEGABYTES)) + " MB")
    
    def communicate(self, text: str, channels: list, input_stream_to_pause: sounddevice.RawInputStream = None):
        """
        Communicates to the user using the channels defined.

        It is an abstraction to deliver in one shot display and audio (and whatever else in the future).
        It is a NOT blocking process, runs every channel in a separate process so they can run in parallel,
        speeding up the overall run.
        
        Every Process needs to be managed a bit different:
        - TTS is an always running Process that listens to a Queue for new messages to say.
        - Display needs to be created per message to show, as we don't have a persistent process
        """

        # In case we want TTS, we need to pause the mic
        # this is done within the TTS process via a shared memory flag that tells the STT to pause

        if self.COMM_TTS in channels:
            # Say the answer
            self._logger.debug("Say Communication")
            # We already have the TTS in a Process, listening for elements in the queue
            self._queue.put((QueueItemType.MESSAGE, text))

        if self.COMM_DISPLAY in channels:
            # Show the answer
            self._logger.debug("Show Communication")
            p_display = Process(target=self._macros.draw_text_bubble, args=(self._display, text, self._display.FONT_MEDIUM))
            p_display.start()


        # Wait for the processes to end
        if self.COMM_TTS in channels:
            # We don't wait, just let it talk. We control the mic via shared_memeory flags
            pass
        if self.COMM_DISPLAY in channels:
            p_display.join()

        

    def _say(speech_instance: PiperMultiprocess, text: str):
        speech_instance.say(text)
        return speech_instance
    
    def _text_has_exit_intention(self, text):
        return text in self._exit_words
    
    def close_nicely(self):
        sw_closing = self._stopwatch.continue_or_start(name="closing")
        self._logger.debug("Closing nicely...")
        # Ensure that everything is waiting for a command
        time.sleep(2)
        # Clean the display
        self._logger.debug("Clearing the display.")
        self._display.clear()
        # Close the Shared Memory
        self._logger.debug("Closing Shared Memory")
        self._shared_memory.shm.close()
        self._shared_memory.shm.unlink()
        # We don't need to ask the process to self-terminate. It will when finishes the job.
        # self._queue.put((QueueItemType.ACTION,QueueItemAction.FINISH))
        self._logger.debug("Is the Speech subprocess still alive? " + ("Yes" if self._speech.is_alive() else "No"))
        if self._speech.is_alive():
            self._logger.debug("Terminating TTS Process")
            self._speech.terminate()
            # kill() does not fail (terminate() sometimes does), but appears to me pretty hardcode.
            # self._speech.kill()

        self._logger.debug("We should be now nicely closed")
        self._logger.debug("⏱️  Closed: " + str(self._stopwatch.stop(sw_closing)))