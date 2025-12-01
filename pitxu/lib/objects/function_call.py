from __future__ import annotations

from google.genai.chats import GenerateContentResponse

class FunctionCallHistory:
    """
    Represents a history of function calls and their responses.
    """
    history: list[FunctionCallPair]

    def __init__(self, history: list[FunctionCallPair] = None):
        if history is not None and isinstance(history, list):
            self.history = history
        else:
            self.history = []

    @staticmethod
    def from_response(response: GenerateContentResponse) -> FunctionCallHistory:

        # The response is a block containing a dialog between the User and the Model.
        # Regarding function calls, think about as the receiver, not the sender:
        # - Entries with role "model" RECEIVE a function call with / without arguments
        # - Entries with role "user" RECEIVE the response of the function call with the result.
        # 
        # For simple function calls, we can just check the last entry with role "model".
        # For complex chains of function calls, we may need to parse the whole history,
        # at least backwards until the first function call of the chain.

        function_call_pairs: list[FunctionCallPair] = []

        try:
            # temporary storage for pairing function call and response
            temporary_pair = FunctionCallPair.from_empty()
            for i in range(len(response.automatic_function_calling_history)):

                content = response.automatic_function_calling_history[i]
                # Having a `parts` as list means that we can have more than one part, even never seen more than 1.
                # This implies that in the future we may have issues if we extend functionality.
                # For now we just assume there is only one part.
                part = content.parts[0] if content.parts and len(content.parts) > 0 else None

                if content.role == "model" \
                    and part is not None \
                    and part.function_call:

                    temporary_pair.set_call(FunctionCall(
                            name=part.function_call.name,
                            arguments=part.function_call.args
                        ))
                    
                elif content.role == "user" \
                    and part is not None \
                    and part.function_response \
                    and temporary_pair is not None:

                    temporary_pair.set_response(FunctionResponse(
                        name=part.function_response.name,
                        response=part.function_response.response))
                    
                    # Assuming that all pairs start with "model" and end with "user"
                    # Once we have registered a response, we can store the pair and reset it
                    function_call_pairs.append(temporary_pair)
                    temporary_pair = FunctionCallPair.from_empty()

        except Exception as e:
            # In case of any error, return an empty history
            print("Error parsing function call history: " + str(e))

        return FunctionCallHistory(history=function_call_pairs)

    def get_last(self) -> FunctionCallPair:
        """
        Gets the last function call pair from the history.

        Returns:
            The last valid FunctionCallPair if available, otherwise None.
        """
        if self.history and len(self.history) > 0:
            for pair in reversed(self.history):
                if pair.is_valid():
                    return pair
        
        # Still here? No valid pair found, it will return empty
        return FunctionCallPair.from_empty()
    
    def get_names(self) -> list[str]:
        """
        Gets the names of all function calls in the history.

        Returns:
            A list of function call names.
        """
        return [pair.function_name for pair in self.history if pair.function_name is not None]

class FunctionCallPair:
    """
    Represents a pair of function call and its corresponding response.
    """
    function_call: FunctionCall = None
    function_response: FunctionResponse = None

    def __init__(self, function_call: FunctionCall = None, function_response: FunctionResponse = None):
        self.function_call = function_call
        self.function_response = function_response

    def has_response(self) -> bool:
        """
        Checks if the FunctionCallPair has a response.

        Returns:
            True if function_response is not None, False otherwise.
        """
        return self.function_response is not None
    
    def has_call(self) -> bool:
        """
        Checks if the FunctionCallPair has a call.

        Returns:
            True if function_call is not None, False otherwise.
        """
        return self.function_call is not None

    def set_call(self, function_call: FunctionCall):
        self.function_call = function_call
    
    def set_response(self, function_response: FunctionResponse):
        self.function_response = function_response
    
    def is_valid(self) -> bool:
        """
        Checks if the FunctionCallPair is valid (both call and response are present and have the same function name).

        Returns:
            True if both function_call and function_response are present, and both have the same name, False otherwise.
        """
        if self.has_call() and self.has_response():
            call_name, response_name = self.get_names()
            return call_name == response_name
        return False
    
    def get_names(self) -> tuple[str, str]:
        """
        Gets the names of the function call and response.

        Returns:
            A tuple containing the names of the function call and response.
            If either is None, returns an empty string for that name.
        """
        call_name = self.function_call.name if self.has_call() else ""
        response_name = self.function_response.name if self.has_response() else ""
        return (call_name, response_name)
    
    @property
    def function_name(self) -> str | None:
        """
        Gets the name of the function call pair

        Returns:
            The name of the function call if the pair is present, otherwise None.
        """
        if self.is_valid():
            return self.function_call.name
        return None

    @staticmethod
    def from_empty() -> FunctionCallPair:
        """
        Creates a FunctionCallPair representing an empty function call.

        Returns:
            A FunctionCallPair with None values.
        """
        return FunctionCallPair()

class FunctionCall:
    """
    Represents a function call made by the chatbot.
    """

    # The unique id of the function call
    # id: str
    # get_weather_forecast_for_today
    name: str
    # {"latitude": 12.3456, "longitude": 7.8901}
    arguments: dict

    def __init__(self, name: str = "", arguments: dict = None):
        self.name = name
        self.arguments = arguments if arguments is not None else {}

class FunctionResponse:
    """
    Represents a response from a function call.
    """

    # get_weather_forecast_for_today
    name: str
    # "result": {
    #     ... weather data ...
    #     }
    # }
    response: dict

    def __init__(self, name: str = "", response: dict = None):
        self.name = name
        self.response = response if response is not None else {}