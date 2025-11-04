from google import genai
from google.genai import types
from google.genai.errors import ServerError

from . import ChatbotProtocol

from pyxavi import Logger, Config, Dictionary, dd

from pitxu.lib.command import CreateNote

import logging

class GeminiChatbot(ChatbotProtocol):
    """
    Using the Gemini API to get answers. Require internet connection.

    https://ai.google.dev/gemini-api/docs/rate-limits
    At the implementation time it uses the Free Tier, Gemini 2.0 Flash.

    - 15 requests per minute
    - 1000000 tokens per minute
    - 1500 requests per day
    """

    create_note_command = CreateNote.generate_gemini_function()

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
        # This setup is focusing into a chat with no commands.
        self._chat = self._client.chats.create(
            model='gemini-2.5-flash',
            config=types.GenerateContentConfig(
                system_instruction=self._config.get("chatbot.system_instruction." + self._parameters.get("language")),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="NONE"))
            )
        )
    
    def ask(self, question: str) -> str:

        self._logger.debug("Question or possible command: " + question)

        if (self._config.get("chatbot.mock", True)):
            return "Chatbot is Mocked. Check the config.\nQuestion: " + question
        else:
            try:
                # return self.parse_command_or_chat(question)
                return self.chat_question(question)
            except ServerError as e:
                return "The server returns an error: " + e.message

            
    def parse_command_or_chat(self, command: str):

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

        # So, how it seems to work:
        #   - You ask to do something
        #   - Most likely, you miss some information, so it returns a chat message asking for that information
        #   - You provide the information
        #   - Then, it returns the function call with all the arguments filled
        #
        # The issue is that I don't know how to enter into this chatty mode of getting parameters and distinguish it from
        #   a normal chat question.

        # Check for a function call
        # dd(response.candidates[0].content.parts[0])
        if response.candidates[0].content.parts[0].function_call:
            self._logger.debug("Found a command, excecuting...")
            function_call = response.candidates[0].content.parts[0].function_call

            self._logger.debug(f"Function to call: {function_call.name}")
            self._logger.debug(f"Arguments: {function_call.args}")

            result = self.create_note(**function_call.args)

            self._logger.debug("Command executed, returning result: " + result)

            return result
        else:
            self._logger.debug("Could not find command, forwarding to chat")
            return self.chat_question(command)
            # return response.text
    
    def chat_question(self, question: str) -> str:
        
        response = self._chat.send_message(question)

        self._logger.debug("Received answer: " + response.text)
        return response.text

    
    def load_commands(self):
        pass
    
    def create_note(self):
        # and here the call to CreateNote.
        pass