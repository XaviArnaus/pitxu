from pyxavi import Config, Dictionary, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.canvas.canvas import Canvas
from pitxu.lib.utils.text import Code

import logging

from google import genai
from google.genai import types

class GoogleSearch(PyXavi, Command):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

    def get_google_search_response_to_a_prompt(self, prompt: str) -> str:
        '''
        Get a response from Google Search related to the given prompt.

        Args:
            prompt (str): The prompt to send to Google Search.

        Returns:
            str: The Gemini response from Google Search as a string.
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
    
    def callback_google_search_response_to_a_prompt(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_google_search_response_to_a_prompt` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_google_search_response_to_a_prompt`.

        """
        # search_term = args.get("prompt", "unknown") if args else "unknown"
        # log.info(f"The term searched in Google from the callback is: {search_term}")

        text = value if isinstance(value, str) else str(value)

        # Does the text contain a code block?
        # We may even have several code blocks.
        code_blocks = []
        while Code.text_includes_code(text):
            code = Code.extract_code_from_text(text)
            if code:
                code = Code.remove_comment_lines_from_code(code)
                code_blocks.append(code)
            text = Code.remove_code_from_text(text)
        
        try:
            if len(code_blocks) > 0:
                # don't go crazy. Log how many do you have, if more than 1, and simply show the first.
                log.info(f"Google Search response includes {len(code_blocks)} code blocks. Showing only the first one.")
                interaction.show_code_block_on_foreground(code=code_blocks[0])
            else:
                text = text[:50] + ("..." if len(text) > 100 else "")
                log.error(f"🔎 Showing extract of Google Search result: [{text}]")
                interaction.show_arbitrary_text_on_foreground_while_speaking(
                    icon="🔎 ",
                    text=text,
                    font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG)
        except Exception as e:
            log.error(f"🛑 Error showing Google searched term on eInk: {e}")
            log.error(full_stack())

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