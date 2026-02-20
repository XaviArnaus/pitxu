from pyxavi import Config, Dictionary, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.canvas.canvas import Canvas
from pitxu.lib.utils.text import Code

import logging

from google import genai
from google.genai import types

class GoogleCode(PyXavi, Command):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

    def get_generate_code(self, prompt: str) -> str:
        '''
        Generate a code block related to the given prompt using Google Gemini.

        Args:
            prompt (str): The prompt to generate the code block from.

        Returns:
            str: The generated code block from Google Gemini as a string.
        '''
        # Apparently the prompt always comes in English, so no need to translate it.
        # Still, looking at the logs, it's not always the case.
        self._xlog.debug(f"Getting Gemini generated code for prompt: [{prompt}] using language [{self._xparams.get('language')}]")

        instructions = {
            "ca": f"Genera un bloc de codi relacionat amb el següent prompt: [{prompt}]. Sigues curt i precís.",
            "es": f"Genera un bloque de código relacionado con el siguiente prompt: [{prompt}]. Sé breve y preciso.",
            "en-us": f"Generate a code block related to the following prompt: [{prompt}]. Be brief and precise.",
            "de": f"Generiere einen Codeblock im Zusammenhang mit dem folgenden Prompt: [{prompt}]. Sei kurz und präzise.",
        }

        tools = [
            # Grounding so it can generate code
            types.Tool(code_execution=types.ToolCodeExecution)
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

        self._xlog.debug(f"Google Gemini response: {response.text}")
        if len(response.candidates) > 1:
            self._xlog.debug(f"Discarded other {len(response.candidates) - 1} candidates to the answer")
            for part in response.candidates[1:]:
                if part.text is not None:
                    dd(part.text)
                if part.executable_code is not None:
                    dd(part.executable_code.code)
                if part.code_execution_result is not None:
                    dd(part.code_execution_result.output)
        return response.executable_code if response.executable_code is not None else response.text
    
    def callback_get_generate_code(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_generate_code` that gets called AFTER chatbot from `main`.

        Args:
            log: The logger to use for logging.
            interaction: The interaction instance to use for showing the code.
            value: The value returned from the Chatbot AFTER it ran `get_generate_code`. It is expected to be a code block in string format.
            args: The arguments passed to the function that this callback is linked to. It may contain useful information like the prompt that generated the code,

        """
        # search_term = args.get("prompt", "unknown") if args else "unknown"
        # log.info(f"The term searched in Google from the callback is: {search_term}")

        text = value if isinstance(value, str) else str(value)

        # Does the text contain a code block?
        # We may even have several code blocks.
        code_blocks = []
        # First remove the code language identifier if it exists
        text = Code.remove_code_language_identifier(text)
        # Get the code blocks from the text
        for code_block in Code.extract_code_from_text(text):
            code_blocks.append(Code.remove_comment_lines_from_code(code_block))
        # Remove the code blocks from the text
        text = Code.remove_all_code_blocks_from_text(text)
        
        try:
            if len(code_blocks) > 0:
                # don't go crazy. Log how many do you have, if more than 1, and simply show the first.
                log.info(f"Gemini's Code Generation response includes {len(code_blocks)} code blocks. Showing only the first one.")
                interaction.show_code_block_on_foreground(code=code_blocks[0])
            else:
                text = text[:50] + ("..." if len(text) > 100 else "")
                log.error(f"🔎 Showing Gemini's Code Generation result: [{text}]")
                interaction.show_arbitrary_text_on_foreground_while_speaking(
                    icon="🔎 ",
                    text=text,
                    font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG)
        except Exception as e:
            log.error(f"🛑 Error showing Gemini's Code Generation result on Foreground: {e}")
            log.error(full_stack())

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_generate_code]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_generate_code":
            return self.callback_get_generate_code
        return self.default_empty_callback