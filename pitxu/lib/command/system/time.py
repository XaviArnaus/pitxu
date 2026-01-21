import time, logging

from pyxavi import Config, Dictionary, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.canvas.canvas import Canvas


class SystemTime(PyXavi, Command):

    format = "%H:%M"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(SystemTime, self).init_pyxavi(config=config, params=params)

    def get_local_system_clock_time(self) -> str:
        '''
        Get the local system clock time in Hour:Minute format.

        Returns:
            str: The current time in Hour:Minute format
        '''
        try:
            return time.strftime(self.format, time.localtime())
        except Exception as e:
            self._xlog.error(f"Error getting current time: {e}")
            return "Error"

    def callback_show_time(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_local_system_clock_time` that gets called AFTER chatbot from `main`.
        
        With this, we have the `main` context to play with for the given function call.
        For example, show the time in the eInk while we TTS the anwer from the Chatbot.

        It is meant to trigger stuff, not to return anything.
        Yeah, it couples it with other parts (why would I couple it with the eInk class?),
        but is thought as a feature of the application. Is the application that needs to evolve
        to abstract these actions (and therefore the communication() method there).

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_local_system_clock_time`.
        
        """
        log.debug(f"The current time in the callback is: {value}")

        try:
            log.info(f"🕒 Showing time on Foreground Display: {value}")
            interaction.show_arbitrary_text_on_eink(
                icon="🕒",
                text=value,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing time on Foreground Display: {e}")
            log.debug(full_stack())

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_local_system_clock_time]
    
    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_local_system_clock_time":
            return self.callback_show_time
        return self.default_empty_callback
