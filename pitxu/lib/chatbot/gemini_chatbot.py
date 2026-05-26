from google import genai
from google.genai import types
from google.genai.errors import ServerError, ClientError, APIError
from google.genai.chats import AsyncChat

from pyxavi import Config, Dictionary, TerminalColor, full_stack, dd

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.chatbot.chatbot_session_manager import ChatbotSessionManager
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from pitxu.lib.objects import FunctionCallPair, FunctionCall, FunctionResponse, ChatbotResponse

from definitions import SHARED_CHATBOT_ANSWER_IS_ERROR

import anyio, math
import fastmcp
from collections import Counter
import logging
import asyncio

class GeminiChatbot(PyXavi):
    """
    Using the Gemini API to get answers. Require internet connection.

    https://ai.google.dev/gemini-api/docs/rate-limits
    
    * Gemini 2.0 Flash.

    - 15 requests per minute
    - 1000000 tokens per minute
    - 1500 requests per day

    * Gemini 2.5 Flash:

    - 10 requests per minute
    - 250000 tokens per minute
    - 250 requests per day
    """

    # Check the available models here:
    # curl "https://generativelanguage.googleapis.com/v1beta/models?key=API_KEY"

    # This is a list of available models to pick from
    # Basically, from better to worse by version
    # Be careful: Several sub-versions of same main version share quotas.
    #   This means that using gemini-2.5-flash-preview-09-2025 and
    #   gemini-2.5-flash will consume the same quota.
    # That's why it's commented here.
    MODELS = [
        # 'gemini-2.5-flash-preview-09-2025',
        # 'gemini-2.5-pro',
        'gemini-3.1-flash-lite',
        'gemini-2.5-flash',
        'gemini-2.5-flash-lite',
        "gemma-3-27b-it",
        # 'gemini-2.0-flash',
    ]
    # We define the Priority model.
    # MODEL_MAIN = 'gemini-2.5-pro'
    MODEL_MAIN = 'gemini-2.5-flash'
    # MODEL_MAIN = 'gemini-3.1-flash-lite'
    # MODEL_MAIN = "gemma-3-27b-it"

    _used_models = []

    ERROR_QUOTA_EXCEEDED = 429

    _client = None
    _chat: AsyncChat = None

    _session_manager: ChatbotSessionManager = None
    _shared_memory: SharedMemoryManager = None

    _mcp_trivago_client: fastmcp.Client = None

    DEFAULT_CHATBOT_NAME = "Pitxu"

    VERBOSE_DEBUG: bool = False
    GENAI_LIB_LOG_LEVEL: int = logging.WARNING
    HTTPCORE_LIB_LOG_LEVEL: int = logging.INFO

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(GeminiChatbot, self).init_pyxavi(config=config, params=params)

        if not self._xparams.key_exists("api_key") or self._xparams.get("api_key", None) is None:
            raise RuntimeError("API Key is mandatory")
        
        if not self._xparams.key_exists("language"):
            raise RuntimeError("Language is mandatory")

        self.initialize()

    def initialize(self):
        if (self._xconfig.get("chatbot.mock", True)):
            self._xlog.warning("Chatbot is mocked, Not initialising it.")
            return False
        self._session_manager = ChatbotSessionManager(config=self._xconfig, params=self._xparams)
        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory_flags()

        # Set the log levels for the Gemini API client and httpcore libraries based on the configuration
        self.GENAI_LIB_LOG_LEVEL = self._xconfig.get("libs_logger.gemini_chatbot.loglevel", self.GENAI_LIB_LOG_LEVEL)
        self.HTTPCORE_LIB_LOG_LEVEL = self._xconfig.get("libs_logger.httpcore.loglevel", self.HTTPCORE_LIB_LOG_LEVEL)

        # define which is the main model (the one initially preferred, if available, and the one we want to use the most)
        self.MODEL_MAIN = self._xconfig.get("chatbot.model", self.MODEL_MAIN)

    def get_session_manager(self):
        return self._session_manager
    
    def get_chat_history(self, curated: bool = False) -> list[types.Content]:
        return self._chat.get_history(curated=curated)
    
    def reset_session(self):
        self._xlog.info("Resetting GeminiChatbot session for the next conversation.")
        # asyncio.run_coroutine_threadsafe(self.initialize_async(tools=self.get_session_manager().tools), asyncio.get_event_loop()).result()
        self._initialize_chat(tools=self.get_session_manager().tools)
    
    def get_chat_history_as_list_of_dicts(self, curated: bool = False) -> list[dict]:
        history = self.get_chat_history(curated=curated)
        history_as_dicts = []
        for item in history:
            parts = item.parts if item.parts is not None else []
            text = "\n".join([part.text for part in parts if part.text is not None])
            functions = {
                "calls": [{ "name": part.function_call.name, "args": part.function_call.args } for part in parts if part.function_call is not None],
                "responses": [{ "name": part.function_response.name, "response": part.function_response.response } for part in parts if part.function_response is not None]
            }
            item_dict = {
                "role": item.role,
                "text": text,
                "functions": functions
            }
            history_as_dicts.append(item_dict)
        return history_as_dicts

    def pick_new_model(self) -> str:
        """
        Picks a new model that hasn't been used yet.
        If all models have been used, resets the used models list and picks again.

        Returns:
            The new model name.
        """
        # Just the ones we CAN pick
        # https://stackoverflow.com/a/55015281/1973860
        available_models = [ v for c in [Counter(self._used_models)] for v in self.MODELS if not c[v] or c.subtract([v]) ]
        # None? Reset. Warning, this can lead to an infinite loop where Pitxu
        # goes through all of them, Google answers 429 in all of them,
        # the list resets and we start again.
        if not available_models:
            self._used_models = []
            available_models = self.MODELS

        # Always preference for the MAIN one
        if self.MODEL_MAIN in available_models:
            new_model = self.MODEL_MAIN
        else:
            new_model = available_models[0]
        
        self._used_models.append(new_model)
        return new_model
    
    def discard_current_model(self):
        """
        Discards the current model from the used models list.
        """
        self._used_models.append(self.MODEL)
    
    def _initialize_internal_loggers(self):
        self._log_debug("Setting Gemini API client log level to: " + str(self.GENAI_LIB_LOG_LEVEL))
        logging.getLogger("google_genai").setLevel(self.GENAI_LIB_LOG_LEVEL)
        self._log_debug("Setting Httpcore client log level to: " + str(self.HTTPCORE_LIB_LOG_LEVEL))
        logging.getLogger("httpcore").setLevel(self.HTTPCORE_LIB_LOG_LEVEL)

    async def initialize_async(self, tools: list, force_model: str = None):
        self._xlog.info("🧠 Initializing GeminiChatbot with forcing the model " + (str(force_model) if force_model is not None else "None"))
        self._client = genai.Client(api_key=self._xparams.get("api_key"))

        self._initialize_internal_loggers()
        
        if force_model is not None and force_model not in self._used_models:
            self.MODEL = force_model
        else:
            self.MODEL = self.pick_new_model()
        self._xlog.info("🧠 Using model: " + str(self.MODEL))
        self._initialize_chat(tools=tools)
        self._xlog.info("🧠 GeminiChatbot initialized successfully with the model: " + self._chat._model)
    
    def _initialize_chat(self, tools: list):
        self._chat = self._client.aio.chats.create(
            model=self.MODEL,
            config=types.GenerateContentConfig(
                system_instruction=self._xconfig.get("chatbot.system_instruction." + self._xparams.get("language")) % self._xconfig.get("chatbot.name", self.DEFAULT_CHATBOT_NAME),
                tools=tools,
                temperature=0.1,
                # The following is a hack to avoid receiving a "Event loop is closed" error from the Gemini API client
                #   or from the Asyncio library, when sending a chatbot message from the Flask server,
                #   only in the second request (the first goes through).
                # One explanation would be in how Flask manages asyncio calls (own thread that gets closed after request):
                #   https://flask.palletsprojects.com/en/stable/async-await/
                # The hack comes from here:
                #   https://stackoverflow.com/questions/78117476/event-loop-is-closed-in-flask-langchain-asyncio-app
                http_options=types.HttpOptions(headers={"Connection": "close"})
            )
        )
        self._xlog.info("🧠 GeminiChatbot initialized successfully with the model: " + self._chat._model)
    
    async def ask_async(self, question: str) -> ChatbotResponse:

            self._xlog.info("❓ Question: \n\n>> " + TerminalColor.RED_BRIGHT + question + TerminalColor.END + "\n")

            if (self._xconfig.get("chatbot.mock", True)):
                return ChatbotResponse(text="Chatbot is Mocked. Check the config.\nQuestion: " + question)
            else:
                retries = 0
                max_retries = 3
                delay_between_retries = 3  # seconds
                outcome: ChatbotResponse = None
                while retries < max_retries:
                    try:
                        if retries > 0:
                            self._xlog.debug("Waiting " + str(delay_between_retries * retries) + " seconds (" + str(retries) + "/" + str(max_retries) + ") before retrying...")
                            await asyncio.sleep(delay_between_retries * retries)

                        response = await self._chat.send_message(question)
                        outcome = ChatbotResponse.from_response(response)
                        if outcome.error is not None:
                            # Turns out that in most cases the answer is None. The tokens are exhausted, so Gemini refuses to answer?
                            # It's largely discussed: https://discuss.ai.google.dev/t/gemini-2-5-pro-with-empty-response-text/81175/71
                            # This may happen due to having too many tools, or too big context.
                            # This started to happen after adding Trivago MCP tool, I guess it consumes a large amount of tokens.
                            # Also the context may be too big if the previous conversation is large.
                            self._xlog.error("🛑 The server answered with an error. The finish reason is: " + outcome.error + 
                                             " and had " + (str(outcome.metadata.total_token_count) + " total tokens" if outcome.metadata and outcome.metadata.total_token_count is not None else ""))
                            dd(response, max_depth=6)
                            if outcome.error == "STOP":
                                if retries < max_retries - 1:
                                    self._xlog.debug("🛠️ Retrying due to STOP finish reason...")
                                    # According to the linked discussion above, we want to use the retry approach.
                                    retries += 1
                                    continue
                                else:
                                    self._xlog.debug("🛠️ Maximum retries reached for STOP finish reason.")
                                    # Fall back to the previous behaviour of answering with an error message.

                            outcome.set_text(self._xconfig.get("language.empty_answer." + self._xparams.get("language")))
                            self._shared_memory.write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, True)
                            # Make him remember that he couldn't answer
                            self._chat.record_history(
                                user_input=types.Content(role="user", parts = [types.Part(text=question)]),
                                model_output=types.Content(role="model", parts = [types.Part(text=outcome.text)]),
                                automatic_function_calling_history=[],
                                is_valid=False
                            )
                        else:
                            self._shared_memory.write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, False)

                        self._xlog.info("🗣️  Answer: \n\n>> " + TerminalColor.ORANGE_BRIGHT + str(outcome.text) + TerminalColor.END + "\n")
                        if outcome.code is not None:
                            self._xlog.info("🗣️ Has Code: \n\n" + TerminalColor.ORANGE_BRIGHT + str(outcome.code) + TerminalColor.END + "\n")
                        self._log_debug("💰 Tokens: " + str(outcome.metadata.total_token_count) if outcome.metadata and outcome.metadata.total_token_count is not None else "?")
                        # We interrupt any retry loop returning directly here
                        return outcome
                    except APIError as e:
                        # Rework this: The APIError is the parent class of ClientError and ServerError
                        # For Quota Exceeded we actually receive a ClientError
                        # It is captured here because it is the parent class
                        self._xlog.error("🛑 API error when asking question to Gemini (" + str(retries) + "/" + str(max_retries) + "): " + str(e.code) + " " + str(e.message)) 
                        message = e.message.split(',')[0] if ',' in e.message else e.message
                        message_short = message
                        retries += 1
                        if e.code == self.ERROR_QUOTA_EXCEEDED:
                            if e.details and "error" in e.details and "details" in e.details["error"] and len(e.details["error"]["details"]) == 3:
                                details = e.details["error"]
                                # There is a "details" inside. It's a list.
                                # - position 0 has help
                                # - position 1 has quota info
                                # - position 2 has retryDelay
                                seconds = str(math.ceil(float(str(details["details"][2]["retryDelay"]).replace("s", "")))) if "retryDelay" in details["details"][2] else None
                                violations = ""
                                if 'violations' in details["details"][1] and len(details["details"][1]['violations']) > 0:
                                    # Violations is also a list of 1 element
                                    quota_metric = str(details["details"][1]['violations'][0]['quotaMetric']).split('_')[-1] if 'quotaMetric' in details["details"][1]['violations'][0] else "metric?"
                                    quota_value = str(details["details"][1]['violations'][0]['quotaValue']) if 'quotaValue' in details["details"][1]['violations'][0] else "value?"
                                    violations = f"\n{quota_metric}: {quota_value}"
                                status = str(details['status']) if 'status' in details else ""
                                message_short = f"{status}{violations}\nRetry after {seconds if seconds is not None else 'some'} seconds."
                                outcome = ChatbotResponse(text=self._xconfig.get("language.quota_exceeded_error." + self._xparams.get("language")) % (seconds if seconds is not None else "some"))
                                # Having details makes us able to draw an error into the eInk.
                                outcome.function_call_history.add_pair(
                                    FunctionCallPair(
                                        function_call=FunctionCall(
                                            name="error",
                                            arguments={"code": e.code, "message": message}),
                                        function_response=FunctionResponse(
                                            name="error",
                                            response={"result": message_short})))
                                # And now, as we have exhausted the quota, let's try to move to the secondary model if possible
                                if self.MODEL == self.MODEL_MAIN:
                                    self._xlog.info("🧠 Switching to another model.")
                                    self.discard_current_model()
                                    await self.initialize_async(tools=self.get_session_manager().tools)
                            else:
                                outcome = ChatbotResponse(text=self._xconfig.get("language.api_error." + self._xparams.get("language")) + " " + str(message))
                            # In case of a quota exceeded, we don't need to retry now.
                            # We answer and let the user decide when to retry.
                            retries = max_retries
                        else:
                            outcome = ChatbotResponse(text=self._xconfig.get("language.api_error." + self._xparams.get("language")) + " " + str(message))
                        self._shared_memory.write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, True)
                        # Make him remember that he couldn't answer, even it was our fault (quota?)
                        self._chat.record_history(
                            user_input=types.Content(role="user", parts = [types.Part(
                                text=question,
                                function_call=types.FunctionCall(
                                    name="error",
                                    args={"code": e.code, "message": message}))]),
                            model_output=types.Content(role="model", parts = [types.Part(
                                text=outcome.text,
                                function_response=types.FunctionResponse(
                                    name="error",
                                    response={"result": message_short}))]),
                            automatic_function_calling_history=[],
                            is_valid=False
                        )
                    except ServerError as e:
                        self._xlog.error("🛑 Server error when asking question to Gemini (" + str(retries) + "/" + str(max_retries) + "): " + str(e.code) + " " + str(e.message))
                        outcome = ChatbotResponse(text=self._xconfig.get("language.server_error." + self._xparams.get("language")) + " " + str(e.message))
                        self._shared_memory.write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, True)
                        # Make him remember that he couldn't answer
                        self._chat.record_history(
                            user_input=types.Content(role="user", parts = [types.Part(text=question)]),
                            model_output=types.Content(role="model", parts = [types.Part(text=outcome.text)]),
                            automatic_function_calling_history=[],
                            is_valid=False
                        )
                        retries += 1
                    except ClientError as e:
                        self._xlog.error("🛑 Client error when asking question to Gemini (" + str(retries) + "/" + str(max_retries) + "): " + str(e.code) + " " + str(e.message))
                        outcome = ChatbotResponse(text=self._xconfig.get("language.client_error." + self._xparams.get("language")) + " " + str(e.message))
                        self._shared_memory.write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, True)
                        # This is an error from our side, so no need to make him remember it
                        retries += 1
                    except anyio.ClosedResourceError as e:
                        self._xlog.error("🛑 ClosedResourceError when asking question to Gemini (" + str(retries) + "/" + str(max_retries) + "): The connection to the MCP server was closed")
                        outcome = ChatbotResponse(text=self._xconfig.get("language.connection_closed_error." + self._xparams.get("language")))
                        self._shared_memory.write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, True)
                        # Make him remember that he couldn't answer
                        self._chat.record_history(
                            user_input=types.Content(role="user", parts = [types.Part(text=question)]),
                            model_output=types.Content(role="model", parts = [types.Part(text=outcome.text)]),
                            automatic_function_calling_history=[],
                            is_valid=False
                        )
                        retries += 1
                    except Exception as e:
                        self._xlog.error("🛑 Unexpected exception when asking question to Gemini (" + str(retries) + "/" + str(max_retries) + "): " + str(e))
                        print(full_stack())
                        outcome = ChatbotResponse(text=self._xconfig.get("language.general_error." + self._xparams.get("language")) + " " + str(e))
                        self._shared_memory.write_shared_memory_flag(SHARED_CHATBOT_ANSWER_IS_ERROR, True)
                        # Make him remember that he couldn't answer
                        self._chat.record_history(
                            user_input=types.Content(role="user", parts = [types.Part(text=question)]),
                            model_output=types.Content(role="model", parts = [types.Part(text=outcome.text)]),
                            automatic_function_calling_history=[],
                            is_valid=False
                        )
                        retries += 1
                return outcome