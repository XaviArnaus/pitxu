from __future__ import annotations

class ArbitraryText:
    text: str

    def __init__(self, text: str):
        self.text = text

class ChatbotAnswer:
    question: str
    answer: str

    was_function_used: bool
    last_function_name: str
    last_function_arguments: dict[str, any]
    last_function_result: any

    is_error: bool
    error_message: str

    def has_question(self) -> bool:
        return self.question is not None and len(self.question.strip()) > 0
    
    def has_answer(self) -> bool:
        return self.answer is not None and len(self.answer.strip()) > 0

    @staticmethod
    def from_dict(data: dict) -> ChatbotAnswer:
        answer = ChatbotAnswer()
        answer.question = data.get("question", None)
        answer.answer = data.get("answer", None)
        answer.was_function_used = data.get("was_function_used", False)
        answer.last_function_name = data.get("last_function_name", None)
        answer.last_function_arguments = data.get("last_function_arguments", None)
        answer.last_function_result = data.get("last_function_result", None)
        answer.is_error = data.get("is_error", False)
        answer.error_message = data.get("error_message", None)

        if answer.last_function_name is not None and answer.was_function_used is False:
            answer.was_function_used = True
        
        if answer.error_message is not None and answer.is_error is False:
            answer.is_error = True

        return answer

class StatusUpdate:
    value: str
    type: StatusType

    def __init__(self, type: StatusType, value: str = None):
        self.type = type
        self.value = value

class StatusType:
    INIT_PHASE = "INIT_PHASE"
    HOLDING_INTERACTION = "HOLDING_INTERACTION"
    ERROR = "ERROR"
    SPEAKING = "SPEAKING"
    THINKING = "THINKING"

class ArbitraryContent:

    icon: str
    text: str
    font_size: int
    header: str
    font_header_size: int
    padding: int

    image_bytes: bytes
    image_dict: dict

    while_talking: bool = False

    def __init__(self, 
                    icon: str = None,
                    text: str = None,
                    font_size: int = 24,
                    header: str = None,
                    font_header_size: int = 32,
                    padding: int = 5,
                    image_bytes: bytes = None,
                    image_dict: dict = None,
                    while_talking: bool = False):
        
        self.icon = icon
        self.text = text
        self.font_size = font_size
        self.header = header
        self.font_header_size = font_header_size
        self.padding = padding
        self.image_bytes = image_bytes
        self.image_dict = image_dict
        self.while_talking = while_talking
