import time

from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.eink import EinkDisplay

from pitxu.lib.objects.point import Point


class SystemTime(PyXavi, Command):

    format = "%H:%M"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

    def get_current_time(self) -> str:
        '''
        Gets the current system time. The date is not included.

        Returns:
            The current time in Hour:Minute format
        '''
        try:
            return time.strftime(self.format, time.localtime())
        except Exception as e:
            self._xlog.error(f"Error getting current time: {e}")
            return "Error"

    def callback_show_time(self, main_instance, value) -> None:
        """
        Callback for `get_current_time` that gets called AFTER chatbot from `main`.
        
        With this, we have the `main` context to play with for the given function call.
        For example, show the time in the eInk while we TTS the anwer from the Chatbot.

        It is meant to trigger stuff, not to return anything.
        Yeah, it couples it with other parts (why would I couple it with the eInk class?),
        but is thought as a feature of the application. Is the application that needs to evolve
        to abstract these actions (and therefore the communication() method there).

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_current_time`.
        
        """
        main_instance._xlog.info(f"The current time in the callback is: {value}")

        try:

            # Apparently I can't get access to the class that lives as a subprocess.
            # display: EinkDisplay = main_instance.get_eInk_display()
            # canvas = display.create_canvas(reset_base_image=True)

            # This works, but it feels too much work for something simple.
            # Taking another route: predefining a generic drawing macro.

            # To workaround that, we create a new EinkDisplay instance here.
            # Be careful. We use some shortcuts to create a canvas,
            # but we should NOT use the Display class directly from here.
            # display: EinkDisplay = EinkDisplay(config=self._xconfig, params=self._xparams)
            # canvas = display.create_canvas(reset_base_image=True)
            # screen_size: Point = display.get_screen_size()
            # # Apparently, the e-ink display is rotated 90 degrees, so swap coordinates for real GPIO work.
            # canvas.text(Point(screen_size.y / 2, screen_size.x / 2).to_image_point(),
            #             text = value,
            #             font = display.FONT_HUGE,
            #             fill = display.COLOR_BLACK,
            #             anchor = "mm",
            #             align = "center")

            # # Show the time in the eInk display
            # image = display.get_image()
            # main_instance.show_image_on_eink(image.tobytes().hex())

            # New approach, using the existing display instance via main
            main_instance._xlog.error(f"🕒 Showing time on eInk: {value}")
            main_instance.show_arbitrary_text_centered_on_eink(value)
        except Exception as e:
            main_instance._xlog.error(f"🛑 Error showing time on eInk: {e}")

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_current_time]
    
    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_current_time":
            return self.callback_show_time
        return self.default_empty_callback
