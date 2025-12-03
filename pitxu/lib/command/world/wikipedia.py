from pyxavi import Config, Dictionary, full_stack
from pitxu.lib.eink.eink import EinkDisplay
from pitxu.lib.utils.api_request import ApiRequest

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.eink import EinkCanvas, Macros
from pitxu.lib.objects import Point, Rectangle

class WorldWikipedia(PyXavi, Command):

    URL = f"https://%s.wikipedia.org/api/rest_v1/page/summary/%s"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

    def get_summary_from_wikipedia_by_term(self, term: str) -> str:
        '''
        Gets the summary from Wikipedia for a specific term.

        Returns:
            The summary in plain text format.
        '''

        # These are the languages we support towards the ones supported by Wikipedia
        switch = {
            "en-us": "en",
            "es": "es",
            "ca": "ca",
            "de": "de",
        }
        lang = switch.get(self._xconfig.get("app.default_language"), "en")

        self._xlog.debug(f"Getting summary for language {lang} from Wikipedia for term: {term}")

        url = WorldWikipedia.URL % (lang, term)
        response = ApiRequest.do(url)
        if response and 'extract' in response:
            return response['extract']
        return "No summary available."
    
    def callback_summary_from_wikipedia_by_term(self, main_instance, value: any, args: dict = None) -> None:
        """
        Callback for `get_summary_from_wikipedia_by_term` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_summary_from_wikipedia_by_term`.

        """
        search_term = args.get("term", "unknown") if args else "unknown"
        main_instance._xlog.info(f"The term searched in Wikipedia from the callback is: {search_term}")

        try:
            # Add an emoji and a percentage sign to the value
            value = f"🌐 {search_term}"

            # Be careful. We use some shortcuts to create a canvas,
            # but we should NOT use the Display class directly from here.
            canvas_handler = EinkCanvas(config=self._xconfig, params=self._xparams)
            screen_size = canvas_handler.get_screen_size()
            canvas = canvas_handler.create_canvas(reset_base_image=True)
            macros = Macros(config=self._xconfig, params=self._xparams)
            padding = 5
            font = canvas_handler.FONT_BIG
            textbox_boundaries = Rectangle(Point(padding, padding), Point(screen_size.x - padding - 2, screen_size.y - padding))
            value = macros.break_line_in_text_if_needed(canvas, value, textbox_boundaries, font)
            canvas.multiline_text(Point(screen_size.x / 2, screen_size.y / 2).to_image_point(),
                        text = value,
                        font = font,
                        fill = canvas_handler.COLOR_BLACK,
                        anchor = "mm",
                        align = "center")

            # Show the time in the eInk display
            main_instance._xlog.error(f"🌐 Showing Wikipedia searched term on eInk: [{search_term}]")
            image = canvas_handler.get_image()
            main_instance.show_image_on_eink({
                "image_data": image.tobytes().hex(),
                "mode": image.mode,
                "size": image.size
            })
        except Exception as e:
            main_instance._xlog.error(f"🛑 Error showing Wikipedia searched term on eInk: {e}")
            main_instance._xlog.error(full_stack())

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