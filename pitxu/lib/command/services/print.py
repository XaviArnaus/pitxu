from pyxavi import Config, Dictionary, full_stack, dd

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.canvas.canvas import Canvas

import logging

import tempfile, subprocess

class ServicePrint(PyXavi, Command):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(ServicePrint, self).init_pyxavi(config=config, params=params)
    
    def send_to_printer(self, text: str) -> bool:
        '''
        Print the given text using the locally configured printer.

        Args:
            text (str): The text to print.

        Returns:
            bool: True if the text was printed successfully, False otherwise.
        '''

        # To do so, it creates a temporary text file, sends it to the printer using the `lp` command,
        # and then deletes the temporary file.

        try:

            printer = self._xconfig.get("services.print.printer")
            self._xlog.debug(f"Printing to printer [{printer}] the following text:\n{text}")

            # Have a temporary file created during this action (Context)
            with tempfile.NamedTemporaryFile(mode='w+', delete=True) as temp_file:
                temp_file.write(text)
                temp_file.flush()  # Ensure all data is written to the file

                # Now print this file using the `lp` command
                print_command = ["lp", "-d", printer, temp_file.name]
                subprocess.run(print_command, check=True)

                # Now that it's printed, the temporary file will be deleted automatically
                self._xlog.debug("Text printed successfully.")

            return True
        except Exception as e:
            self._xlog.error(f"🛑 Error printing text to {printer}: {e}")
            self._xlog.debug(full_stack())
            return False
    
    def callback_print(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `print` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `print`.
            args: Additional arguments passed to the callback.
        """
        try:
            if value:
                log.debug("🖨️ Text printed.")
                interaction.show_arbitrary_text_on_foreground_while_speaking(
                    icon="🖨️",
                    text="Text printed ✅",
                    font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG)
            else:
                log.error("🛑 Failed to print text.")
                interaction.show_arbitrary_text_on_foreground_while_speaking(
                    icon="🖨️",
                    text="Failed to print text ❌",
                    font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG)
        except Exception as e:
            log.error(f"🛑 Error in print callback: {e}")
    
    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.send_to_printer]
    
    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "send_to_printer":
            return self.callback_print