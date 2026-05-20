from pyxavi import Config, Dictionary, full_stack
from pitxu.lib.utils.api_request import ApiRequest

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.canvas.canvas import Canvas

import logging

class WorldWikipedia(PyXavi, Command):

    URL = f"https://%s.wikipedia.org/api/rest_v1/page/summary/%s"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

    def get_summary_from_wikipedia_by_term(self, term: str) -> str:
        '''
        Get the summary from Wikipedia for a specific term to search for.

        Args:
            term (str): The term to search for on Wikipedia.

        Returns:
            str: The summary in plain text format, or a message indicating no summary is available.
        '''

        # These are the languages we support towards the ones supported by Wikipedia
        lang = switch.get(self._xconfig.get("app.default_language"), "en")

        self._xlog.debug(f"Getting summary for language {lang} from Wikipedia for term: {term}")

        url = WorldWikipedia.URL % (lang, term)
        response = ApiRequest.do(url)
        if response and 'extract' in response:
            return response['extract']
        return "No summary available."
    
    def callback_summary_from_wikipedia_by_term(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_summary_from_wikipedia_by_term` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_summary_from_wikipedia_by_term`.

        """
        search_term = args.get("term", "unknown") if args else "unknown"
        log.info(f"The term searched in Wikipedia from the callback is: {search_term}")

        try:
            log.error(f"🌐 Showing Wikipedia searched term on eInk: [{search_term}]")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="🌐",
                text=search_term,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG)
        except Exception as e:
            log.error(f"🛑 Error showing Wikipedia searched term on eInk: {e}")
            log.error(full_stack())

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_summary_from_wikipedia_by_term]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_summary_from_wikipedia_by_term":
            return self.callback_summary_from_wikipedia_by_term
        return self.default_empty_callback