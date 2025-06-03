from multiprocessing import Pool
import logging

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary

from pitxu.lib.utils.text import Text
from pitxu.lib.chatbot.gemini_chatbot import GeminiChatbot
from pitxu.lib.eink.display import EinkDisplay
from pitxu.lib.eink.macros import Macros
from pitxu.lib.speech_to_text.vosk import Vosk
from pitxu.lib.text_to_speech.piper import Piper

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

    EXIT_WORDS = ["exit", "quit", "sortir", "adéu"]
    COMM_DISPLAY = "display"
    COMM_TTS = "tts"

    def __init__(self, config: Config = None, params: Dictionary = None):

        # Possible runtime parameters
        self._parameters = params

        # Config is mandatory
        if config is None:
            raise RuntimeError("Config can not be None")
        self._config = config

        # Common Logger
        self._logger = Logger(config=config, base_path=params.get("base_path", "")).get_logger()
    
    def run(self):

        # Initialise eInk Display and the helper macros
        self._logger.debug("Initialising the e-Ink")
        self._display = EinkDisplay(config=self._config, params=self._parameters)
        self._macros = Macros(self._config, params=self._parameters)

        # Startup splash. It should be understood as a "Loading..." screen.
        self._macros.startup_splash(self._display)
        time.sleep(2)

        # Initialise Speech-to-Text
        self._logger.debug("Initialising the Speech-to-Text")
        self._dictate = Vosk(self._config, params=self._parameters)

        # Initialise Text-To-Speech
        self._logger.debug("Initialising the Text-to-Speech")
        self._speech = Piper(self._config, params=self._parameters)

        # Initialise Chatbot
        self._logger.debug("Initialising the Chatbot Client")
        self._chatbot = GeminiChatbot(config=self._config, params=self._parameters)

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
                self.communicate("Hola sóc el Pitxu. Diga'm alguna cosa",
                                 [self.COMM_TTS, self.COMM_DISPLAY],
                                 input_stream)

                question = ""
                while(not self._text_has_exit_intention(question)):
                    # Recognize what comes from the microphone
                    question = self._dictate.recognize()
                    if (question == None or question.strip() == ""):
                        continue
                    self._logger.debug(">> Recognised dictate")

                    # Avoid calling the Chatbot when exiting
                    if self._text_has_exit_intention(question):
                        # Just assume a goodbye
                        answer = "Fins la propera! Adéu!"
                    else:
                        # Here we start with the Chatbot
                        answer = self._chatbot.ask(question)
                    
                    # Clean the answer first, just in case
                    answer = Text.remove_emojis(answer)

                    # Answer
                    self.communicate(answer, [self.COMM_TTS, self.COMM_DISPLAY], input_stream)

        except KeyboardInterrupt:
            self._logger.info("Pressed Control + C")
        
        # Final clean
        time.sleep(5)
        self._display.clear()
        self._speech.terminate()
    
    def communicate(self, text: str, channels: list, input_stream_to_pause: sounddevice.RawInputStream = None):

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
            # pool.apply(self._speech.say, args=(text, input_stream_to_pause))
            self._speech.say(text, input_stream_to_pause=input_stream_to_pause)

        # Wait for the processes to end
        pool.close()
        pool.join()

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
        return text in ["exit", "quit", "sortir", "adéu"]