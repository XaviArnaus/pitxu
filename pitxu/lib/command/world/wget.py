from pyxavi import Config, Dictionary
from pitxu.lib.utils.wget import Wget

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command

class WorldWget(PyXavi, Command):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(WorldWget, self).init_pyxavi(config=config, params=params)

    def get_content_from_url(self, url: str) -> str | bool:
        '''
        Get the content from the given URL.

        Args:
            url (str): The URL to get the content from.


        Returns:
            str | bool: The content as a string, or False if not found.
        '''
        wget = Wget(config=self._xconfig, params=self._xparams)
        result = wget.get(url)
        
        return result
    
    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_content_from_url]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        return self.default_empty_callback