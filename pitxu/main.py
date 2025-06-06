from multiprocessing import Pool
import logging

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary

from pitxu.lib.utils import Text, Stopwatch
from pitxu.lib.chatbot import GeminiChatbot
from pitxu.lib.eink import EinkDisplay, Macros
from pitxu.lib.speech_to_text import Vosk
from pitxu.lib.text_to_speech import Piper


import sounddevice
import time

class Main:

    _config: Config = None
    _logger: logging = None

    _display: EinkDisplay = None
    _macros: Macros = None
    _chatbot: GeminiChatbot = None
    _dictate: Vosk = None
    _speech: Piper = None

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

        # Initial Language
        self._parameters.set("language", config.get("app.default_language", self.CATALAN))

        # Supported Languages
        self._supported_languages = config.get("languages.supported_languages")

        self._stopwatch = Stopwatch()
    
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
            self._logger.info("Pressed Control + C")
        
        # Final clean
        time.sleep(5)
        self._display.clear()
        self._speech.terminate()
        self._logger.info("⏱️  Final Stopwatch report:\n" + self._stopwatch.stop_and_report())
    
    def communicate(self, text: str, channels: list, input_stream_to_pause: sounddevice.RawInputStream = None):
        """
        Communicates to the user using the channels defined.

        It is an abstraction to deliver in one shot display and audio (and whatever else in the future).
        It is a blocking process, but runs every channel in a separate process so they can run in parallel,
        speeding up the overall run.
        Current status: TTS can't be added into a separate process due to an issue when pickle it:
            "TypeError: cannot pickle 'onnxruntime.capi.onnxruntime_pybind11_state.InferenceSession' object"
        """

        # TODO: Tried to 
        # In case we want TTS, we need to pause the mic
        # Has to happen in the main thread, as the RawInputStream can't be pickled to be sent as a param to the Pool
        # if self.COMM_TTS in channels and input_stream_to_pause is not None:
        #     input_stream_to_pause.stop()

        # We want parallelism. Create a Multiprocessing Pool
        pool = Pool(processes=2)

        if self.COMM_DISPLAY in channels:
            # Show the answer
            self._logger.debug("Show Communication")
            pool.apply_async(self._macros.draw_text_bubble, args=(self._display, text, self._display.FONT_MEDIUM))

        if self.COMM_TTS in channels:
            # Say the answer
            self._logger.debug("Say Communication")
            # Feels like the object is pickled into the thread, and fails.
            # see: https://github.com/microsoft/onnxruntime/pull/800
            # error: "TypeError: cannot pickle 'onnxruntime.capi.onnxruntime_pybind11_state.InferenceSession' object"
            # pool.apply(self._speech.say, args=(text, input_stream_to_pause))
            # pool.apply(self._speech.say, args=(text))
            self._speech.say(text, input_stream_to_pause=input_stream_to_pause)

        # Wait for the processes to end
        pool.close()
        pool.join()

        # In case we want TTS, we need to release the mic
        # Has to happen in the main thread, as the RawInputStream couldn't be pickled to be sent as a param to the Pool

        # if self.COMM_TTS in channels and input_stream_to_pause is not None:
        #     input_stream_to_pause.start()

        #### Originally was:

        # if self.COMM_DISPLAY in channels:
        #     # Show the answer
        #     self._logger.debug("Show Communication")
        #     self._macros.draw_text_bubble(self._display, text, self._display.FONT_MEDIUM)

        # if self.COMM_TTS in channels:
        #     # Say the answer
        #     self._logger.debug("Say Cmmunication")
        #     self._speech.say(text, input_stream_to_pause=input_stream_to_pause)

    
    def _text_has_exit_intention(self, text):
        return text in self._exit_words

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
        
        # Initialise Speech-to-Text
        self._logger.debug("Initialising the Speech-to-Text with language [" + self._parameters.get("language") + "]")
        self._dictate = Vosk(self._config, params=self._parameters)

        # Initialise Text-To-Speech
        self._logger.debug("Initialising the Text-to-Speech with language [" + self._parameters.get("language") + "]")
        self._speech = Piper(self._config, params=self._parameters)

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