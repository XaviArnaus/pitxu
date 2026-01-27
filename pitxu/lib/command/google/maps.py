from pyxavi import Config, Dictionary, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.canvas.canvas import Canvas

import logging

from google import genai
from google.genai import types

class GoogleMaps(PyXavi, Command):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(GoogleMaps, self).init_pyxavi(config=config, params=params)

    def get_google_maps_response_to_a_prompt(self, prompt: str) -> str:
        '''
        Get a response from Google Maps related to the given prompt.

        Args:
            prompt (str): The prompt to send to Google Maps.

        Returns:
            str: The Gemini response from Google Maps as a string.
        '''
        # Apparently the prompt always comes in English, so no need to translate it.
        # Still, looking at the logs, it's not always the case.
        self._xlog.debug(f"Getting Google Maps response for prompt: [{prompt}] using language [{self._xparams.get('language')}]")

        instructions = {
            "ca": "Usa Google Maps per obtenir la resposta sobre distàncies, rutes i localitzacions en el mapa."
                    "Sigues curt i precís. Si necessites rebre una ubicació, demana les coordenades geogràfiques al usuari.",
            "es": "Usa Google Maps para obtener la respuesta sobre distancias, rutas y localizaciones en el mapa."
                    "Sé breve y preciso. Si necesitas recibir una ubicación, pide las coordenadas geográficas al usuario.",
            "en-us": "Use Google Maps to obtain the answer about distances, routes, and locations on the map."
                    "Be brief and precise. If you need to receive a location, ask the user for the geographic coordinates.",
            "de": "Verwenden Sie Google Maps, um die Antwort zu Entfernungen, Routen und Standorten auf der Karte zu erhalten."
                    "Seien Sie kurz und präzise. Wenn Sie einen Standort erhalten müssen, fragen Sie den Benutzer nach den geografischen Koordinaten.",
        }

        tools = [
            # Grounding so it can use Google Maps
            types.Tool(google_maps=types.GoogleMaps())
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

        self._xlog.debug(f"Google Maps response: {response.text}")
        if len(response.candidates) > 1:
            self._xlog.debug("Discarded other candidates to the answer:" + "\n\n>".join(response.candidates))
        return response.text
    
    def callback_google_maps_response_to_a_prompt(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_google_maps_response_to_a_prompt` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_google_maps_response_to_a_prompt`.

        """
        dd(args)
        search_term = args.get("prompt", "unknown") if args else "unknown"
        log.info(f"The term searched in Google Maps from the callback is: {search_term}")

        try:
            log.error(f"📍 Showing Google Maps searched term on eInk: [{search_term}]")
            interaction.show_arbitrary_text_on_foreground(
                icon="📍",
                text=search_term,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG)
        except Exception as e:
            log.error(f"🛑 Error showing Google Maps searched term on eInk: {e}")
            log.error(full_stack())

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_google_maps_response_to_a_prompt]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_google_maps_response_to_a_prompt":
            return self.callback_google_maps_response_to_a_prompt
        return self.default_empty_callback