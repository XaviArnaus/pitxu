from typing import Protocol, runtime_checkable
from pyxavi.config import Config

@runtime_checkable
class ChatbotProtocol(Protocol):

    def __init__(self, config: Config = None, params: dict = {}) -> None:
        """Initializing the class"""
    
    def load(self):
        """Loading stuff the class"""
    
    def ask(self, question: str) -> str:
        """Asking things"""