import base64
from pyxavi import Config, Dictionary, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.objects.chatbot_response import ChatbotResponse
from pitxu.lib.objects.function_call import FunctionCallPair

import numpy as np
import json
import requests

class Client(PyXavi):

    ENDPOINT_STATUS: str = "status"
    ENDPOINT_TRANSCRIBE: str = "transcribe"
    ENDPOINT_ASK_CHATBOT: str = "ask_chatbot"
    ENDPOINT_SYNTHESIZE: str = "synthesize"

    PROTOCOL: str = "http"

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config, params: Dictionary):
        super(Client, self).init_pyxavi(config=config, params=params)
    
    def initialize(self):
        pass

    def status(self):
        return self._do_get_request(endpoint=self.ENDPOINT_STATUS)

    def transcribe(self, data_bytes: bytes) -> str:
        encoded_bytes = base64.b64encode(data_bytes).decode('utf-8')
        return self._do_post_request(endpoint=self.ENDPOINT_TRANSCRIBE, data={"data_bytes": encoded_bytes})

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

    def _do_get_request(self, endpoint: str):
        url = self._build_url(endpoint=endpoint)
        response = requests.get(url)
        return json.loads(response.content)
    
    def _do_post_request(self, endpoint: str, data: dict):
        url = self._build_url(endpoint=endpoint)
        response = requests.post(url, json=data)
        return json.loads(response.content)
    
    def _build_url(self, endpoint: str):
        url = self.PROTOCOL + "://" + \
            self._xconfig.get("client.host") + \
            ":" + str(self._xconfig.get("client.port")) + \
            "/" + endpoint
        return url
