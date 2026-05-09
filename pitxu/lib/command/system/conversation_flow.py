from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command


class SystemConversationFlow(PyXavi, Command):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(SystemConversationFlow, self).init_pyxavi(config=config, params=params)

    def user_intends_to_end_conversation(self) -> bool:
        '''
        Handles the user's intention to end the conversation.

        Returns:
            bool: Returns True if the user intends to end the conversation, False otherwise.
        '''
        try:
            self._xlog.info(f"User intends to end the conversation.")
            return True
        except Exception as e:
            self._xlog.error(f"Error handling user's intention to end the conversation: {e}")
            return False
    
    def get_tool_definition(self) -> list[callable]:
        """
        Return the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.user_intends_to_end_conversation]
    
    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Get the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        return self.default_empty_callback
