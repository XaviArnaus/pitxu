import time, logging

from pyxavi import Config, Dictionary, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.utils.system import System


class SystemNetwork(PyXavi, Command):

    format = "%H:%M"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(SystemNetwork, self).init_pyxavi(config=config, params=params)

    def get_local_network_ip(self) -> str:
        '''
        Get the local network IP address.

        Returns:
            str: The local network IP address or an error message if it cannot be retrieved.
        '''
        try:
            return System.get_default_network_interface().get("ip")
        except Exception as e:
            self._xlog.error(f"🛑 Error getting current IP address: {e}")
            return "Error getting the IP address: " + str(e)

    def callback_get_local_network_ip(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `get_local_network_ip` to show the local network IP address on the Foreground Display.

        Args:
            log: The logger to use for logging.
            interaction: The interaction object to use for interacting with the user.
            value: The value returned by the `get_local_network_ip` function.
            args: Additional arguments that may be needed for the callback.
        
        """

        try:
            log.info(f"⚙️ Showing local network IP on Foreground Display: {value}")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="🌐",
                text=value,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing local network IP on Foreground Display: {e}")
            log.debug(full_stack())

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_local_network_ip]
    
    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_local_network_ip":
            return self.callback_get_local_network_ip
        return self.default_empty_callback
