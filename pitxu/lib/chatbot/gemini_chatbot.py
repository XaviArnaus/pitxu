from google import genai
from google.genai import types
from google.genai.errors import ServerError
from google.genai.chats import AsyncChat

from pyxavi import Logger, Config, Dictionary, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.chatbot.chatbot_session_manager import ChatbotSessionManager
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager

from definitions import SHARED_CHATBOT_ANSWER_IS_ERROR

import logging, time, anyio
import fastmcp

class GeminiChatbot(PyXavi):
    """
    Using the Gemini API to get answers. Require internet connection.

    https://ai.google.dev/gemini-api/docs/rate-limits
    At the implementation time it uses the Free Tier, Gemini 2.0 Flash.

    - 15 requests per minute
    - 1000000 tokens per minute
    - 1500 requests per day
    """

    _client = None
    _chat: AsyncChat = None

    _session_manager: ChatbotSessionManager = None
    _shared_memory: SharedMemoryManager = None
    _safe_close_callback = None

    _mcp_trivago_client: fastmcp.Client = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(GeminiChatbot, self).init_pyxavi(config=config, params=params, safe_close_callback=None)

        if not self._xparams.key_exists("api_key") or self._xparams.get("api_key", None) is None:
            raise RuntimeError("API Key is mandatory")
        self.initialize()

    def initialize(self):
        if (self._xconfig.get("chatbot.mock", True)):
            self._xlog.warning("Chatbot is mocked, Not initialising it.")
            return False
        self._client = genai.Client(api_key=self._xparams.get("api_key"))
        self._session_manager = ChatbotSessionManager(config=self._xconfig, params=self._xparams, safe_close_callback=None)
        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory_flags()
    
    def get_session_manager(self):
        return self._session_manager
    
    def get_chat_history(self):
        return self._chat.get_history()
    
    async def initialize_async(self, tools: list):
        self._chat = self._client.aio.chats.create(
                model='gemini-2.5-flash',
                config=types.GenerateContentConfig(
                    system_instruction=self._xconfig.get("chatbot.system_instruction." + self._xparams.get("language")),
                    tools=tools,
                    temperature=0.1
                )
            )
    
    async def ask_async(self, question: str) -> str:

            self._xlog.debug("❓ Question: " + question)

            if (self._xconfig.get("chatbot.mock", True)):
                return "Chatbot is Mocked. Check the config.\nQuestion: " + question
            else:
                retries = 0
                max_retries = 3
                delay_between_retries = 3  # seconds
                outcome = ""
                while retries < max_retries:
                    try:
                        if retries > 0:
                            self._xlog.debug("Waiting " + str(delay_between_retries * retries) + " seconds (" + str(retries) + "/" + str(max_retries) + ") before retrying...")
                            time.sleep(delay_between_retries * retries)
                        
                        # response = await chat.send_message(question)
                        response = await self._chat.send_message(question)
                        text = response.text
                        if text is None:
                            # Turns out that in most cases the tokens are exhausted, so Gemini refuses to answer.
                            # This may happen due to having too many tools, or too big context.
                            # This started to happen after adding Trivago MCP tool, I guess it consumes a large amount of tokens.
                            # Also the context may be too big if the previous conversation is large.
                            finish_reason = response.candidates[0].finish_reason if response.candidates and len(response.candidates) > 0 else "unknown"
                            self._xlog.error("🛑 The server answered with a null response. The finish reason is: " + finish_reason)
                            text = self._xconfig.get("language.empty_answer." + self._xparams.get("language"))
                            self._shared_memory.write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, True)
                            # Make him remember that he couldn't answer
                            self._chat.record_history(
                                user_input=types.Content(text=question, role="user"),
                                model_output=types.Content(text=text, role="model"),
                                is_valid=False
                            )
                        else:
                            self._shared_memory.write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, False)
                        self._xlog.debug("🗣️ Received answer: " + str(text))
                        return text
                    except ServerError as e:
                        self._xlog.error("🛑 Server error when asking question to Gemini (" + str(retries) + "/" + str(max_retries) + "): " + str(e.code) + " " + str(e.message))
                        outcome = self._xconfig.get("language.server_error." + self._xparams.get("language")) + " " + str(e.message)
                        self._shared_memory.write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, True)
                        # Make him remember that he couldn't answer
                        self._chat.record_history(
                            user_input=types.Content(text=question, role="user"),
                            model_output=types.Content(text=text, role="model"),
                            is_valid=False
                        )
                        retries += 1
                    except anyio.ClosedResourceError as e:
                        self._xlog.error("🛑 ClosedResourceError when asking question to Gemini (" + str(retries) + "/" + str(max_retries) + "): The connection to the MCP server was closed")
                        outcome = self._xconfig.get("language.connection_closed_error." + self._xparams.get("language"))
                        self._shared_memory.write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, True)
                        # Make him remember that he couldn't answer
                        self._chat.record_history(
                            user_input=types.Content(text=question, role="user"),
                            model_output=types.Content(text=text, role="model"),
                            is_valid=False
                        )
                        retries += 1
                    except Exception as e:
                        self._xlog.error("🛑 Unexpected exception when asking question to Gemini (" + str(retries) + "/" + str(max_retries) + "): " + str(e))
                        print(full_stack())
                        outcome = self._xconfig.get("language.general_error." + self._xparams.get("language")) + " " + str(e)
                        self._shared_memory.write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, True)
                        # Make him remember that he couldn't answer
                        self._chat.record_history(
                            user_input=types.Content(text=question, role="user"),
                            model_output=types.Content(text=text, role="model"),
                            is_valid=False
                        )
                        retries += 1
                return outcome