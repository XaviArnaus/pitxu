import logging

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary

from pitxu.lib.chatbot.gemini_chatbot import GeminiChatbot
from pitxu.lib.eink.display import EinkDisplay
from pitxu.lib.eink.macros import Macros
from pitxu.lib.dto.font_size import FontSize
from pitxu.lib.speech_to_text.vosk import Vosk

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

        # Initialise Speech-to-text
        self._logger.debug("Initialising the Speech-to-Text")
        speech = Vosk(self._config, params=self._parameters)

        # Initialise Chatbot
        self._logger.debug("Initialising the Chatbot Client")
        chatbot = GeminiChatbot(config=self._config, params=self._parameters)

        self._logger.debug("Initialising the Speech-to-Text")
        speech.initialize()

        try:
            # Read from microphone
            # Correct format for Vosk is PCM 16khz 16bit mono
            with sounddevice.RawInputStream(samplerate=speech.samplerate,
                                blocksize = 8000, 
                                device=speech.device,
                                dtype="int16", 
                                channels=1, 
                                callback=speech.callback):
                
                # Ready splash
                macros.ready_splash(display)
                time.sleep(1)

                question = ""
                while(not self._text_has_exit_intention(question)):
                    # Recognize what comes from the microphone
                    question = speech.recognize()
                    if (question == None or question.strip() == ""):
                        continue

                    # Avoid calling the Chatbot when exiting
                    if self._text_has_exit_intention(question):
                        # Just assume a goodbye
                        answer = "Fins la propera! Adéu!"
                    else:
                        # Here we start with the Chatbot
                        answer = chatbot.ask(question)

                    # Show the answer
                    canvas = display.create_canvas(reset_base_image=True)
                    macros.draw_text_bubble(canvas, answer, display.FONT_MEDIUM)
                    display.display()

        except KeyboardInterrupt:
            self._logger.info("Pressed Control + C")
        
        # Final clean
        time.sleep(5)
        display.clear()
    
    def _text_has_exit_intention(self, text):
        return text in ["exit", "quit", "sortir", "adéu"]