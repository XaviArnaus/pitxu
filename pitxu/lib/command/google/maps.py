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
            interaction.show_arbitrary_text_on_foreground_while_speaking(
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

# 2026-05-07 18:44:35,345 [MainProcess      MainThread            ] INFO     httpx        HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent "HTTP/1.1 200 OK"
# 2026-05-07 18:44:35,347 [MainProcess      asyncio_0             ] DEBUG    pitxu        Getting Google Maps response for prompt: [distance between Dusseldorf, Germany and Altafulla, Spain] using language [en-us]
# 2026-05-07 18:44:43,146 [MainProcess      asyncio_0             ] INFO     httpx        HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent "HTTP/1.1 200 OK"
# 2026-05-07 18:44:43,147 [MainProcess      asyncio_0             ] DEBUG    pitxu        Google Maps response: I am unable to provide the distance between Dusseldorf, Germany and Altafulla, Spain using the available tools.
# 2026-05-07 18:44:44,350 [MainProcess      MainThread            ] INFO     httpx        HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent "HTTP/1.1 200 OK"
# 2026-05-07 18:44:44,351 [MainProcess      MainThread            ] INFO     pitxu        🗣️  Answer: 

# >> I apologize, but I'm still unable to retrieve the distance information using the available tools. It seems there's a persistent technical issue. I recommend trying again later.

# 2026-05-07 18:44:44,351 [MainProcess      MainThread            ] DEBUG    pitxu        🤖 Unsetting Chatbot as busy.
# 2026-05-07 18:44:44,351 [MainProcess      MainThread            ] INFO     pitxu        Reacting to a Chatbot answer: 
#         - Text: I apologize, but I'm still unable to retrieve the distance information using the available tools. It seems there's a persistent technical issue. I recommend trying again later.
#         - Function Calls: ['get_google_maps_response_to_a_prompt']
#         - Code blocks: 0
# 2026-05-07 18:44:44,352 [MainProcess      MainThread            ] DEBUG    pitxu        ⚡️ Reacting to function call: get_google_maps_response_to_a_prompt
# 2026-05-07 18:44:44,352 [MainProcess      MainThread            ] DEBUG    pitxu        ↩️  Reacting to a function call with a client callback: get_google_maps_response_to_a_prompt
# 2026-05-07 18:44:44,352 [MainProcess      MainThread            ] DEBUG    pitxu        📺 Executing callback with value: I am unable to provide the distance between Dusseldorf, Germany and Altafulla, Spain using the available tools.
# 2026-05-07 18:44:44,352 [MainProcess      MainThread            ] DEBUG    pitxu        💤  Setting idle mode off.
# 2026-05-07 18:44:44,352 [MainProcess      MainThread            ] DEBUG    pitxu        Waiting for queue dsi_lcd_queue to empty. Has now: 0 elements.
# 2026-05-07 18:44:44,352 [MainProcess      MainThread            ] DEBUG    pitxu        The queue dsi_lcd_queue is empty now. I've sleept 0s.
# 2026-05-07 18:44:44,352 [MainProcess      MainThread            ] DEBUG    pitxu        Waiting for the process dsi_lcd_busy to idle. It's now: IDLE.
# 2026-05-07 18:44:44,352 [MainProcess      MainThread            ] DEBUG    pitxu        The process dsi_lcd_busy is idle now. I've slept 0s.
# (dict[1]){"prompt": (str[57])"distance between Dusseldorf, Germany and Altafulla, Spain"}
# 2026-05-07 18:44:44,352 [MainProcess      MainThread            ] INFO     pitxu        The term searched in Google Maps from the callback is: distance between Dusseldorf, Germany and Altafulla, Spain
# 2026-05-07 18:44:44,352 [MainProcess      MainThread            ] ERROR    pitxu        📍 Showing Google Maps searched term on eInk: [distance between Dusseldorf, Germany and Altafulla, Spain]
# 2026-05-07 18:44:44,352 [MainProcess      MainThread            ] DEBUG    pitxu        Waiting for queue dsi_lcd_queue to empty. Has now: 0 elements.
# 2026-05-07 18:44:44,352 [MainProcess      MainThread            ] DEBUG    pitxu        The queue dsi_lcd_queue is empty now. I've sleept 0s.
# 2026-05-07 18:44:44,352 [DsiLcd-3         MainThread            ] INFO     pitxu        👀 Showing arbitrary text on DSI LCD while speaking.
# 2026-05-07 18:44:44,356 [MainProcess      MainThread            ] DEBUG    pitxu        🗣️ Triggering speech interaction: I apologize, but I'm still unable to retrieve the distance information using the available tools. It seems there's a persistent technical issue. I recommend trying again later.
# 2026-05-07 18:44:44,356 [MainProcess      MainThread            ] DEBUG    pitxu        🗣️ Sending SAY command to Background display
# 2026-05-07 18:44:44,356 [MainProcess      MainThread            ] DEBUG    pitxu        🗣️ Sending SAY command to Speaker
# 2026-05-07 18:44:44,356 [MainProcess      MainThread            ] DEBUG    pitxu        🗣️ Waiting for Speaker and Display to start and finish speaking
# 2026-05-07 18:44:44,356 [MainProcess      MainThread            ] DEBUG    pitxu        Waiting for the process speaker_busy to be busy. It's now: BUSY.
# 2026-05-07 18:44:44,356 [MainProcess      MainThread            ] DEBUG    pitxu        The process speaker_busy is busy now. I've slept 0s.
# 2026-05-07 18:44:44,356 [MainProcess      MainThread            ] DEBUG    pitxu        Waiting for the process speaker_busy to idle. It's now: BUSY.
# 2026-05-07 18:44:44,356 [DsiLcd-3         MainThread            ] INFO     pitxu        👄 Showing KITT mouth on DSI LCD.
# 2026-05-07 18:44:44,356 [Piper-2          MainThread            ] DEBUG    pitxu        Saying [I apologize, but I'm still unable to retrieve the distance information using the available tools. It seems there's a persistent technical issue. I recommend trying again later.]