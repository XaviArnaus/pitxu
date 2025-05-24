import logging

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary

from pitxu.lib.chatbot.geminai_chatbot import GeminaiChatbot
from pitxu.lib.eink.display import EinkDisplay
from pitxu.lib.eink.macros import Macros
from pitxu.lib.dto.font_size import FontSize

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
        display = EinkDisplay(config=self._config, params=self._parameters)
        macros = Macros(self._config, params=self._parameters)
        #display.test()

        # Initialise Chatbot
        self._logger.debug("Initialising the Chatbot Client")
        chatbot = GeminaiChatbot(config=self._config, params=self._parameters)

        question = ""
        while(not self._text_has_exit_intention(question)):
            # Listen to the input of the user
            question = input("Introdueix la teva pregunta: [\"exit\" to leave]: \n")

            # Avoid calling the Chatbot when exiting
            if self._text_has_exit_intention(question):
                # Just assume a goodbye
                answer = "Fins la propera! Adéu! Chúus!"
            else:
                # Here we start with the Chatbot
                answer = chatbot.ask(question)

            # Show the answer
            canvas = display.create_canvas()
            macros.draw_text_bubble(canvas, answer, display.FONT_MEDIUM)
            display.display()
    
    def _text_has_exit_intention(self, text):
        return text in ["exit", "quit", "sortir", "adéu"]