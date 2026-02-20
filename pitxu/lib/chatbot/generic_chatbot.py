from google import genai
from google.genai import types
from google.genai.errors import ServerError, ClientError, APIError
from google.genai.chats import AsyncChat

from pyxavi import Config, Dictionary, TerminalColor, full_stack, dd

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.chatbot.chatbot_session_manager import ChatbotSessionManager
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from pitxu.lib.objects import FunctionCallPair, FunctionCall, FunctionResponse, ChatbotResponse
from pitxu.lib.microservice.client import Client

from definitions import SHARED_CHATBOT_ANSWER_IS_ERROR

import time, anyio, math
import fastmcp
from collections import Counter
import logging

class GenericChatbot(PyXavi):
    """
    This is a generic chatbot class that simply sends a request to get a response.
    """

    _used_models = []

    ERROR_QUOTA_EXCEEDED = 429

    _client: Client = None

    _session_manager: ChatbotSessionManager = None
    _shared_memory: SharedMemoryManager = None

    _mcp_trivago_client: fastmcp.Client = None

    VERBOSE_DEBUG: bool = True
    GENAI_LIB_LOG_LEVEL: int = logging.WARNING
    HTTPCORE_LIB_LOG_LEVEL: int = logging.INFO

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(GenericChatbot, self).init_pyxavi(config=config, params=params)

    def initialize(self):
        if (self._xconfig.get("chatbot.mock", True)):
            self._xlog.warning("Chatbot is mocked, Not initialising it.")
            return False

        self._client = Client(config=self._xconfig, params=self._xparams)
        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory_flags()

    async def ask_async(self, question: str) -> ChatbotResponse:

        self._xlog.info("❓ Question: \n\n>> " + TerminalColor.RED_BRIGHT + question + TerminalColor.END + "\n")

        if (self._xconfig.get("chatbot.mock", True)):
            return ChatbotResponse(text="Chatbot is Mocked. Check the config.\nQuestion: " + question)
        else:
            outcome: ChatbotResponse = None
            try:
                
                outcome = self._client.ask_chatbot(question=question)
                if outcome.error is not None:
                    
                    outcome.set_text(self._xconfig.get("language.api_error." + self._xparams.get("language")) + " " + str(outcome.error))
                    self._shared_memory.write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, True)

                else:
                    self._shared_memory.write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, False)

                self._xlog.info("🗣️  Answer: \n\n>> " + TerminalColor.ORANGE_BRIGHT + str(outcome.text) + TerminalColor.END + "\n")
                
            except Exception as e:
                self._xlog.error("🛑 Unexpected exception when asking question to Generic Chatbot client: " + str(e))
                print(full_stack())
                outcome = ChatbotResponse(text=self._xconfig.get("language.general_error." + self._xparams.get("language")) + " " + str(e))
                self._shared_memory.write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, True)

            return outcome