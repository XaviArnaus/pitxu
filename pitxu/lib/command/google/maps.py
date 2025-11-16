from pyxavi import Config
from pitxu.lib.abstract.pyxavi import PyXavi

from google import genai
from google.genai import types

class GoogleMaps(PyXavi):

    def __init__(self, config: Config = None, params: dict = None):
        super(GoogleMaps, self).init_pyxavi(config=config, params=params)

    def get_google_maps_response_to_a_prompt(self, prompt: str) -> str:
        '''
        Gets a response from Google Maps related to the given prompt.

        Returns:
            The Gemini response from Google Maps as a string.
        '''
        # Apparently the prompt always comes in English, so no need to translate it.
        # Still, looking at the logs, it's not always the case.
        self._xlog.debug(f"Getting Google Maps response for prompt: [{prompt}] using language [{self._xparams.get('language')}]")

        instructions = {
            "ca": f"Usa Google Maps per obtenir la resposta. Sigues curt i precís. Si necessites rebre una ubicació, demana les coordenades geogràfiques al usuari.",
            "es": f"Usa Google Maps para obtener la respuesta. Sé breve y preciso.",
            "en-us": f"Use Google Maps to obtain the answer. Be brief and precise.",
            "de": f"Verwenden Sie Google Maps, um die Antwort zu erhalten. Seien Sie kurz und präzise.",
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