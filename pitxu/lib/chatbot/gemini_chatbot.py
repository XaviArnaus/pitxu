from google import genai
from google.genai import types
from google.genai.errors import ServerError

from . import ChatbotProtocol

from pyxavi import Logger, Config, Dictionary

from pitxu.lib.command import SystemDate, SystemTime, WorldPosition, WorldWeather, WorldWikipedia, GoogleMaps, GoogleSearch

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

    _client = None
    _xparams: Dictionary = None
    _xconfig: Config = None
    _xlog: logging
    _chat = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        self._xparams = params
        if not self._xparams.key_exists("api_key") or self._xparams.get("api_key", None) is None:
            raise RuntimeError("API Key is mandatory")

        if config is None:
            raise RuntimeError("Config can not be None")

        self._xconfig = config
        self._xlog = Logger(config=config, base_path=self._xparams.get("base_path", "")).get_logger()
        self.initialize()

    def initialize(self):
        if (self._xconfig.get("chatbot.mock", True)):
            self._xlog.warning("Chatbot is mocked, Not initialising it.")
            return False
        
        self._client = genai.Client(api_key=self._xparams.get("api_key"))

        google_maps_command = GoogleMaps(config=self._xconfig, params=self._xparams)
        google_search_command = GoogleSearch(config=self._xconfig, params=self._xparams)
        world_position_command = WorldPosition(config=self._xconfig, params=self._xparams)

        tools = [
            # Grounding workaround so it can use Google Search
            google_search_command.get_google_search_response_to_a_prompt,
            # Grounding workaround so it can use Google Maps
            google_maps_command.get_google_maps_response_to_a_prompt,
            # # Custom Commands
            SystemDate.get_current_date,
            SystemTime.get_current_time,
            world_position_command.get_latitude_and_longitude_from_location,
            world_position_command.get_latitude_and_longitude_from_current_location,
            world_position_command.get_latitude_and_longitude_from_address,
            WorldWeather.get_weather_forecast,
            WorldWikipedia.get_summary_from_wikipedia_by_term,
        ]
        self._chat = self._client.chats.create(
            model='gemini-2.5-flash',
            config=types.GenerateContentConfig(
                system_instruction=self._xconfig.get("chatbot.system_instruction." + self._xparams.get("language")),
                tools=tools
            )
        )
    
    def ask(self, question: str) -> str:

        self._xlog.debug("Question: " + question)

        if (self._xconfig.get("chatbot.mock", True)):
            return "Chatbot is Mocked. Check the config.\nQuestion: " + question
        else:
            try:
                # return self.parse_command_or_chat(question)
                return self.chat_question(question)
            except ServerError as e:
                return "The server returns an error: " + e.message
            except Exception as e:
                return "The server returns an unexpected error: " + e
    
    def chat_question(self, question: str) -> str:
        
        response = self._chat.send_message(question)

        self._xlog.debug("Received answer: " + str(response.text))
        if len(response.candidates) > 1:
            self._xlog.debug("Discarded other candidates to the answer:" + "\n\n>".join(response.candidates))
        return response.text

    
    def load_commands(self):
        pass
    
    def create_note(self):
        # and here the call to CreateNote.
        pass