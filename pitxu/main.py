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

    EXIT_WORDS = ["exit", "quit", "sortir", "adéu"]

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
        display = EinkDisplay(config=self._config, params=self._parameters)
        macros = Macros(self._config, params=self._parameters)

        # Startup splash. It should be understood as a "Loading..." screen.
        macros.startup_splash(display)
        time.sleep(2)

        # Initialise Speech-to-Text
        self._logger.debug("Initialising the Speech-to-Text")
        dictate = Vosk(self._config, params=self._parameters)

        # Initialise Text-To-Speech
        self._logger.debug("Initialising the Text-to-Speech")
        speech = Piper(self._config, params=self._parameters)

        # Initialise Chatbot
        self._logger.debug("Initialising the Chatbot Client")
        chatbot = GeminiChatbot(config=self._config, params=self._parameters)

        self._logger.debug("Initialising the Speech-to-Text")
        dictate.initialize()

        try:
            # Read from microphone
            # Correct format for Vosk is PCM 16khz 16bit mono
            with sounddevice.RawInputStream(samplerate=dictate.samplerate,
                                blocksize = 0, 
                                device=dictate.device,
                                dtype="int16", 
                                channels=1, 
                                callback=dictate.callback):
                
                # Ready splash
                macros.ready_splash(display)
                time.sleep(1)

                # Welcome speech
                speech.say("Hola sóc el Pitxu. Diga'm alguna cosa")

                question = ""
                while(not self._text_has_exit_intention(question)):
                    # Recognize what comes from the microphone
                    question = dictate.recognize()
                    if (question == None or question.strip() == ""):
                        continue

                    # Avoid calling the Chatbot when exiting
                    if self._text_has_exit_intention(question):
                        # Just assume a goodbye
                        answer = "Fins la propera! Adéu!"
                    else:
                        # Here we start with the Chatbot
                        answer = chatbot.ask(question)
                    
                    # Clean the answer first, just in case
                    answer = Text.remove_emojis(answer)

                    # Show the answer
                    canvas = display.create_canvas(reset_base_image=True)
                    macros.draw_text_bubble(canvas, answer, display.FONT_MEDIUM)
                    display.display()

                    # Say the answer
                    speech.say(answer)

        except KeyboardInterrupt:
            self._logger.info("Pressed Control + C")
        
        # Final clean
        time.sleep(5)
        display.clear()
    
    def _text_has_exit_intention(self, text):
        return text in ["exit", "quit", "sortir", "adéu"]