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

        try:
            # Relating the issue that the dictate detects the sound output as something to parse:
            # Apparently the [with:] block here activates the input stream BEFORE the loop and then
            # still active during the whole loop time.
            # Maybe it's better to return the [stream] object and control the dictate with it
            # stream.start() and stream.stop(), as seen here:
            # https://stackoverflow.com/a/71524248/1973860


            # Read from microphone
            # Correct format for Vosk is PCM 16khz 16bit mono
            with sounddevice.RawInputStream(samplerate=dictate.samplerate,
                                blocksize = 0, 
                                device=dictate.device,
                                dtype="int16", 
                                channels=1, 
                                callback=dictate.callback):
                
                # Ready splash
                self._logger.debug(">> Ready Splash")
                macros.ready_splash(display)
                time.sleep(1)

                # Welcome speech
                self._logger.debug(">> Say Greeting")
                speech.say("Hola sóc el Pitxu. Diga'm alguna cosa")
                self._logger.debug(">> Finished saying Greeting")

                question = ""
                while(not self._text_has_exit_intention(question)):
                    # Recognize what comes from the microphone
                    self._logger.debug(">> Recognise dictate")
                    question = dictate.recognize()
                    if (question == None or question.strip() == ""):
                        self._logger.debug(">> Not recognized anything meaningul")
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
                    self._logger.debug(">> Show Answer")
                    canvas = display.create_canvas(reset_base_image=True)
                    macros.draw_text_bubble(canvas, answer, display.FONT_MEDIUM)
                    display.display()

                    # Say the answer
                    self._logger.debug(">> Say Answer")
                    speech.say(answer)
                    self._logger.debug(">> Finished saying Answer")

        except KeyboardInterrupt:
            self._logger.info("Pressed Control + C")
        
        # Final clean
        time.sleep(5)
        display.clear()
    
    def _text_has_exit_intention(self, text):
        return text in ["exit", "quit", "sortir", "adéu"]