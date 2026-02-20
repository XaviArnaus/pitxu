import base64
from pyxavi import Config, Dictionary, dd

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.microservice.microservice_base import MicroserviceBase
from pitxu.lib.objects.chatbot_response import ChatbotResponse
from pitxu.lib.objects.function_call import FunctionCallPair

import numpy as np
import json, logging
import requests

class Client(PyXavi, MicroserviceBase):

    ENDPOINT_STATUS: str = "status"
    ENDPOINT_TRANSCRIBE: str = "transcribe"
    ENDPOINT_ASK_CHATBOT: str = "ask_chatbot"
    ENDPOINT_SYNTHESIZE: str = "synthesize"

    VERBOSE_DEBUG: bool = True
    URLLIB3_LIB_LOG_LEVEL: int = logging.INFO

    def __init__(self, config: Config, params: Dictionary):
        super(Client, self).init_pyxavi(config=config, params=params)

        # Set the log levels for the Piper libraries based on the configuration
        self.URLLIB3_LIB_LOG_LEVEL = self._xconfig.get("libs_logger.urllib3.loglevel", self.URLLIB3_LIB_LOG_LEVEL)
        self._log_debug("Setting Server log level to: " + str(self.URLLIB3_LIB_LOG_LEVEL))
        logging.getLogger("urllib3").setLevel(self.URLLIB3_LIB_LOG_LEVEL)
    
    def initialize(self):
        pass

    def status(self):
        return self._do_get_request(endpoint=self.ENDPOINT_STATUS)

    def transcribe(self, data_bytes: bytes, sample_rate: int) -> str | None:
        encoded_bytes = base64.b64encode(data_bytes).decode('utf-8')
        server_response = self._do_post_request(endpoint=self.ENDPOINT_TRANSCRIBE, data={
            "data_bytes": encoded_bytes,
            "sample_rate": sample_rate
        })
        dd(server_response)
        if server_response.get("status", "ko") == "ok":
            return {
                "received_bytes_length": server_response.get("received_bytes_length", None),
                "frames": server_response.get("frames", None),
                "error": server_response.get("error", None),
                "transcription": server_response.get("transcription", None)
            }
        else:
            return {
                "received_bytes_length": server_response.get("received_bytes_length", None),
                "frames": server_response.get("frames", None),
                "error": server_response.get("error", "Unknown error"),
                "transcription": None
            }

    def ask_chatbot(self, question: str) -> ChatbotResponse:
        server_response = self._do_post_request(endpoint=self.ENDPOINT_ASK_CHATBOT, data={"question": question})
        return ChatbotResponse.from_dict({
            "text": server_response.get("answer", ""),
            "function_call_history": server_response.get("function_call_history", None),
            "error": server_response.get("error", None)
        })

    def synthesize(self, text: str) -> dict:
        server_response = self._do_post_request(endpoint=self.ENDPOINT_SYNTHESIZE, data={"text": text})
        if server_response.get("status", "ko") == "ok":
            audio_bytes = base64.b64decode(server_response.get("audio_bytes", ""))
            sample_rate = server_response.get("sample_rate", 22050)
            return {
                "audio_bytes": np.frombuffer(audio_bytes, dtype=np.int16),
                "sample_rate": sample_rate
            }
        else:
            raise Exception(f"Error during synthesis: {server_response.get('error', 'Unknown error')}")
