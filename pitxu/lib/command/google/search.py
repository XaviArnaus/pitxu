from pyxavi import Config, Dictionary, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.eink import EinkCanvas, Macros
from pitxu.lib.objects import Point, Rectangle

from google import genai
from google.genai import types

class GoogleSearch(PyXavi, Command):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

    def get_google_search_response_to_a_prompt(self, prompt: str) -> str:
        '''
        Gets a response from Google Search related to the given prompt.

        Returns:
            The Gemini response from Google Search as a string.
        '''
        # Apparently the prompt always comes in English, so no need to translate it.
        # Still, looking at the logs, it's not always the case.
        self._xlog.debug(f"Getting Google Search response for prompt: [{prompt}] using language [{self._xparams.get('language')}]")

        instructions = {
            "ca": f"Usa Google Search per obtenir la resposta. Sigues curt i precís.",
            "es": f"Usa Google Search para obtener la respuesta. Sé breve y preciso.",
            "en-us": f"Use Google Search to obtain the answer. Be brief and precise.",
            "de": f"Verwenden Sie Google Search, um die Antwort zu erhalten. Seien Sie kurz und präzise.",
        }

        tools = [
            # Grounding so it can use Google Search
            types.Tool(google_search=types.GoogleSearch())
        ]
        client = genai.Client(api_key=self._xparams.get("api_key"))
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=instructions[self._xparams.get('language')],
                # system_instruction=instructions["en-us"],
                tools=tools
            )
        )

        self._xlog.debug(f"Google Search response: {response.text}")
        if len(response.candidates) > 1:
            self._xlog.debug("Discarded other candidates to the answer:" + "\n\n>".join(response.candidates))
        return response.text
    
    def callback_google_search_response_to_a_prompt(self, main_instance, value: any, args: dict = None) -> None:
        """
        Callback for `get_google_search_response_to_a_prompt` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_google_search_response_to_a_prompt`.

        """
        dd(args)
        search_term = args.get("prompt", "unknown") if args else "unknown"
        main_instance._xlog.info(f"The term searched in Google from the callback is: {search_term}")

        try:
            # Add an emoji and a percentage sign to the value
            value = f"🔎 {search_term}"

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
            main_instance._xlog.error(f"🔎 Showing Google searched term on eInk: [{search_term}]")
            image = canvas_handler.get_image()
            main_instance.show_image_on_eink({
                "image_data": image.tobytes().hex(),
                "mode": image.mode,
                "size": image.size
            })
        except Exception as e:
            main_instance._xlog.error(f"🛑 Error showing Google searched term on eInk: {e}")
            main_instance._xlog.error(full_stack())

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_google_search_response_to_a_prompt]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_google_search_response_to_a_prompt":
            return self.callback_google_search_response_to_a_prompt
        return self.default_empty_callback