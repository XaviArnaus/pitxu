from google import genai
from google.genai import types
from google.genai.errors import ServerError

from . import ChatbotProtocol

from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary

from pitxu.lib.command import CreateNote

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

    create_note_command = {
        "name": "self.create_note",
            "description": "Creates a note file",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The title of the note",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date of the meeting (e.g., '2024-07-29')",
                    },
                    "time": {
                        "type": "string",
                        "description": "Time of the meeting (e.g., '15:00')",
                    },
                    "body": {
                        "type": "string",
                        "description": "The body of the note",
                    },
                },
                "required": ["title", "body"],
            },
        }

    _client = None
    _parameters: Dictionary = None
    _config: Config = None
    _logger: logging
    _chat = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        self._parameters = params
        if not self._parameters.key_exists("api_key") or self._parameters.get("api_key", None) is None:
            raise RuntimeError("API Key is mandatory")

        if config is None:
            raise RuntimeError("Config can not be None")

        self._config = config
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()
        self.initialize()

    def initialize(self):
        if (self._config.get("chatbot.mock", True)):
            self._logger.warning("Chatbot is mocked, Not initialising it.")
            return False
        
        self._client = genai.Client(api_key=self._parameters.get("api_key"))
        self._chat = self._client.chats.create(
            model='gemini-2.0-flash',
            config=types.GenerateContentConfig(system_instruction=self._config.get("chatbot.system_instruction." + self._parameters.get("language")))
        )
    
    def ask(self, question: str) -> str:

        self._logger.debug("Question: " + question)

        if (self._config.get("chatbot.mock", True)):
            return "Chatbot is Mocked. Check the config.\nQuestion: " + question
        else:
            try:

                response = self._chat.send_message(question)

                self._logger.debug("Received answer: " + response.text)
                return response.text
            except ServerError as e:
                return "The server returns an error: " + e.message
    
    def response(self, command: str):
        self._logger.debug("Command: " + command)

        if (self._config.get("chatbot.mock", True)):
            return "Chatbot is Mocked. Check the config.\Command: " + command
        else:
            try:

                tools = types.Tool(function_declarations=[self.create_note_command])
                config = types.GenerateContentConfig(
                    tools=[tools],
                    system_instruction=self._config.get("chatbot.system_instruction." + self._parameters.get("language"))
                )

                response = self._client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=command,
                    config=config,
                )

                self._logger.debug("Received answer: " + response.text)

                # Check for a function call
                if response.candidates[0].content.parts[0].function_call:
                    self._logger.debug("Found a command, excecuting...")
                    function_call = response.candidates[0].content.parts[0].function_call
                    print(f"Function to call: {function_call.name}")
                    print(f"Arguments: {function_call.args}")
                    #  In a real app, you would call your function here:
                    #  result = schedule_meeting(**function_call.args)
                    result = self.create_note(**function_call.args)
                else:
                    self._logger.debug("Could not find command, forwarding to chat")
                    return self.ask(command)
            except ServerError as e:
                return "The server returns an error: " + e.message

    
    def load_commands(self):
        pass
    
    def create_note(self):
        # and here the call to CreateNote.
        pass