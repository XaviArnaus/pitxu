import ollama

from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.command import SystemDate, SystemTime, WorldPosition, WorldWeather, WorldWikipedia, GoogleMaps, GoogleSearch

from pitxu.lib.chatbot.chatbot_session_manager import ChatbotSessionManager

import logging

class OllamaChatbot(PyXavi):
    """
    Using the Ollama models to get answers, intended to be 100% offline. 
    Requires Ollama to be installed and models downloaded. See the README.
    May do internet calls from the custom commands (Tools/Function Calling)
    """

    _ollama = None
    _session_manager: ChatbotSessionManager = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(OllamaChatbot, self).init_pyxavi(config=config, params=params)
        self.initialize()

    def initialize(self):
        if (self._xconfig.get("chatbot.mock", True)):
            self._xlog.warning("Chatbot is mocked, Not initialising it.")
            return False
        self._session_manager = ChatbotSessionManager(config=self._xconfig, params=self._xparams)
        
        # self._ollama = ollama.Client(
        #     host='http://localhost:11434',

        #     model="jobautomation/OpenEuroLLM-Catalan",
        #     system=self._xconfig.get("chatbot.system_instruction." + self._xparams.get("language"))
        # )

        # google_maps_command = GoogleMaps(config=self._xconfig, params=self._xparams)
        # google_search_command = GoogleSearch(config=self._xconfig, params=self._xparams)
        # world_position_command = WorldPosition(config=self._xconfig, params=self._xparams)

        # tools = [
        #     # Grounding workaround so it can use Google Search
        #     google_search_command.get_google_search_response_to_a_prompt,
        #     # Grounding workaround so it can use Google Maps
        #     google_maps_command.get_google_maps_response_to_a_prompt,
        #     # # Custom Commands
        #     SystemDate.get_current_date,
        #     SystemTime.get_current_time,
        #     world_position_command.get_latitude_and_longitude_from_location,
        #     world_position_command.get_latitude_and_longitude_from_current_location,
        #     world_position_command.get_latitude_and_longitude_from_address,
        #     WorldWeather.get_weather_forecast,
        #     WorldWikipedia.get_summary_from_wikipedia_by_term,
        # ]
        # self._chat = self._client.chats.create(
        #     model='gemini-2.5-flash',
        #     config=types.GenerateContentConfig(
        #         system_instruction=self._xconfig.get("chatbot.system_instruction." + self._xparams.get("language")),
        #         tools=tools
        #     )
        # )
    
    def get_session_manager(self):
        return self._session_manager
    
    def ask(self, question: str) -> str:

        self._xlog.debug("Question: " + question)

        if (self._xconfig.get("chatbot.mock", True)):
            return "Chatbot is Mocked. Check the config.\nQuestion: " + question
        else:
            try:
                answer = self.chat_question(question)
                chatbot_response = self.build_chatbot_response(answer)
                return chatbot_response
            except Exception as e:
                return "The server returns an unexpected error: " + e
    
    def chat_question(self, question: str) -> str:

        response: ollama.ChatResponse = ollama.chat(
            # model="jobautomation/OpenEuroLLM-Catalan",    # Really slow
            # model="qwen3:0.6b",                           # Also slow, bad in responding.
            # model="mistral",                              # ~7s, catalan sounds spanish.
            # model="stablelm-zephyr",                      # ~6s, bad in catalan.
            # was: model="hdnh2006/salamandra-7b-instruct",      # It's enough fast, ~2s, and good in catalan.
            # model="gemma3:4b",                            # Mega slow. Avoid.
            model="gemma3:1b",                        
            messages=[
                {"role": "system", "content": self._xconfig.get("chatbot.system_instruction." + self._xparams.get("language"))},
                {"role": "user", "content": question}
            ]
        )
        answer = response['message']['content']

        self._xlog.debug("Received answer: " + str(answer))
        return answer
    
    def build_chatbot_response(self, answer: str):
        # Currently Ollama does not provide function calling or metadata.
        from pitxu.lib.objects.chatbot_response import ChatbotResponse
        return ChatbotResponse(
            text=answer,
            function_call_history=None,
            error=None,
            metadata=None
        )