class Command:
    """
    Abstract base class for all commands.
    """
    
    def get_tool_definition(self) -> list[callable]:
        """
        Gets the list that defines the tool for this command,
        ready to be used as a tool definition in a language model.

        This is the only one method that must be implemented by subclasses,
        as it defines the functions that the command provides,
        and is used by the system to register the tools.

        Returns:
            A list defining the tools included in this class.
        """
        raise NotImplementedError("Command " + self.__class__.__name__ + " must implement get_tool_definition method.")
    
    def get_function_names(self) -> list[str]:
        """
        Gets the list of function names defined in this command.

        It is used by ChatbotSessionManager.get_client_callbacks_by_function_name() to map function names to callbacks.

        Returns:
            A list of function names.
        """
        return [func.__name__ for func in self.get_tool_definition()]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        Args:
            function_name: The name of the function to get the callback for.

        Returns:
            The callback function corresponding to the given function name, or a default callback if not found.
        """
        return self.default_empty_callback

    def default_empty_callback(self, log, interaction, value: any = None, args: dict = None):
        pass
