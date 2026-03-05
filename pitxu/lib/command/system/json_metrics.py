import time

from pyxavi import Config, Dictionary, full_stack, dd

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.utils.json_logger import JsonLogger
from pitxu.lib.utils.xtime import Xtime

import logging

from datetime import datetime


class SystemJsonMetrics(PyXavi, Command):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(SystemJsonMetrics, self).init_pyxavi(config=config, params=params)

    def get_metrics_between_datetimes(self, start_time: str, end_time: str) -> str:
        f'''
        Get the system metrics between the specified start and end times.

        Args:
            start_time (str): The start time for the metrics in {Xtime.FORMAT} format.
            end_time (str): The end time for the metrics in {Xtime.FORMAT} format.

        Returns:
            list[dict]: A list of log entries between the specified times.
        '''
        try:
            start_datetime = Xtime.str_to_datetime(start_time)
            end_datetime = Xtime.str_to_datetime(end_time)
            json_logger = JsonLogger(config=self._xconfig, params=self._xparams)
            return json_logger.get_logs(start_datetime, end_datetime)
        except Exception as e:
            self._xlog.error(f"🛑 Error getting metrics: {e}")
            return "Error"
    
    def callback_get_metrics_between_datetimes(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_metrics_between_datetimes` that gets called AFTER chatbot from `main`.

        Args:
            log: The logger to use for logging.
            interaction: The Interaction object to use for showing the metrics on the Foreground Display.
            value: The value returned by the `get_metrics_between_datetimes` function, that will be shown on the Foreground Display.
            args: The arguments passed to the `get_metrics_between_datetimes` function, that can be used for logging or showing on the Foreground Display.
        
        Returns:
            None

        """
        log.info(f"The Get Metrics callback returned: {len(value)} log entries. Args were: {args}")
        dd(args)

        try:
            # Get a datetime object from the value
            text = f"Metrics from {args.get('start_time')} to {args.get('end_time')}:\n{len(value)} log entries."

            log.error(f"📄 Showing metrics on Foreground Display: {value}")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📄",
                text=text,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_MEDIUM)
        except Exception as e:
            log.error(f"🛑 Error showing metrics on Foreground Display: {e}")
            log.debug(full_stack())

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_metrics_between_datetimes]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_metrics_between_datetimes":
            return self.callback_get_metrics_between_datetimes
        return self.default_empty_callback