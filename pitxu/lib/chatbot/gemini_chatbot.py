from google import genai
from google.genai import types

from pitxu.lib.chatbot.chatbot_protocol import ChatbotProtocol

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary

import logging

class GeminiChatbot(ChatbotProtocol):
    """
    Using the Gemini API to get answers. Require internet connection.

    https://ai.google.dev/gemini-api/docs/rate-limits
    At the implementation time it uses the Free Tier, Geminii 2.0 Flash.

    - 15 requests per minute
    - 1000000 tokens per minute
    - 1500 requests per day
    """

    _client = None
    _parameters: Dictionary = None
    _config: Config = None
    _logger: logging

    def __init__(self, config: Config = None, params: Dictionary = None):
        self._parameters = params
        if not self._parameters.key_exists("api_key"):
            raise RuntimeError("API Key is mandatory")

        if config is None:
            raise RuntimeError("Config can not be None")

        self._config = config
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()
        self.load()

    def load(self):
        if (self._config.get("chatbot.mock", True)):
            self._logger.warning("Chatbot is mocked, Not initialising it.")
            return False
        self._client = genai.Client(api_key=self._parameters.get("api_key"))
    
    def ask(self, question: str) -> str:

        self._logger.debug("Question: " + question)

        if (self._config.get("chatbot.mock", True)):
            return "Chatbot is Mocked. Check the config.\nQuestion: " + question
        else:
            response = self._client.models.generate_content(
                model="gemini-2.0-flash",
                config=types.GenerateContentConfig(system_instruction=self._config.get("chatbot.system_instruction")),
                contents=question
            )

            self._logger.debug("Received answer: " + response.text)
            return response.text