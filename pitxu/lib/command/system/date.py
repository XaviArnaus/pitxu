import time

from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.eink import EinkCanvas
from pitxu.lib.objects import Point

from datetime import datetime


class SystemDate(PyXavi, Command):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

    format = "%Y-%m-%d"  # E.g., 2023-12-25
    displayed_format = "%d.%m.%Y"  # E.g., 25.12.2023

    def get_current_date_without_time(self) -> str:
        '''
        Gets the current system date. The time is not included.
        
        Returns:
            The current date in Year-Month-Day format
        '''
        try:
            return time.strftime(self.format, time.localtime())
        except Exception as e:
            self._xlog.error(f"Error getting current date: {e}")
            return "Error"
    
    def callback_show_date(self, main_instance, value: any, args: dict = None) -> None:
        """
        Callback for `get_current_date_without_time` that gets called AFTER chatbot from `main`.

        With this, we have the `main` context to play with for the given function call.
        For example, show the date in the eInk while we TTS the anwer from the Chatbot.

        It is meant to trigger stuff, not to return anything.
        Yeah, it couples it with other parts (why would I couple it with the eInk class?),
        but is thought as a feature of the application. Is the application that needs to evolve
        to abstract these actions (and therefore the communication() method there).

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_current_date_without_time`.

        """
        main_instance._xlog.info(f"The current date in the callback is: {value}")

        try:
            # Get a datetime object from the value
            date_obj = datetime.strptime(value, self.format)
            value = date_obj.strftime(self.displayed_format)

            # Be careful. We use some shortcuts to create a canvas,
            # but we should NOT use the Display class directly from here.
            canvas_handler = EinkCanvas(config=self._xconfig, params=self._xparams)
            screen_size = canvas_handler.get_screen_size()
            canvas = canvas_handler.create_canvas(reset_base_image=True)
            canvas.text(Point(screen_size.x / 2, screen_size.y / 2).to_image_point(),
                        text = f"📆 {value}",
                        font = canvas_handler.FONT_BIG,
                        fill = canvas_handler.COLOR_BLACK,
                        anchor = "mm",
                        align = "center")

            # Show the time in the eInk display
            main_instance._xlog.error(f"📆 Showing date on eInk: {value}")
            image = canvas_handler.get_image()
            main_instance.show_image_on_eink(image.tobytes().hex())
        except Exception as e:
            main_instance._xlog.error(f"🛑 Error showing date on eInk: {e}")

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_current_date_without_time]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_current_date_without_time":
            return self.callback_show_date
        return self.default_empty_callback