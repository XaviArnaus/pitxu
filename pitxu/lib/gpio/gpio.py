from pyxavi import Config, Dictionary, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi

from .mocked_gpiozero import MockedButton, MockedButtons

class Gpio(PyXavi):

    mocked_buttons_manager: MockedButtons = None
    buttons: dict[str, MockedButton] = {}
    button_pins_per_name: dict[str, int] = {}

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Gpio, self).init_pyxavi(config=config, params=params)

    def initialize_buttons(self):
        # Initialise GPIO buttons
        self._xlog.info("Initialising GPIO buttons...")

        # First of all, in case we are mocked, initialize the singleton that manages the buttons
        if self._xconfig.get("gpio.mock", False):
            self._xlog.warning("Using mocked GPIO buttons")
            self.mocked_buttons_manager = MockedButtons(config=self._xconfig, params=self._xparams)

        # Gather the definitions from the config and initialise them
        try:
            button_definitions = self._xconfig.get("gpio.buttons", [])
            for button in button_definitions:
                self.buttons[button["name"]] = self._new_button(button["pin"], button["mocked_as"])
                self.button_pins_per_name[button["name"]] = button["pin"]
        except (Exception, RuntimeError, SystemExit) as e:
            self._xlog.error(f"Error initializing GPIO buttons: {e}")
            self._xlog.debug(full_stack())
        
        # Now if the mocked buttons manager exists, start listening
        if self.mocked_buttons_manager is not None:
            self.mocked_buttons_manager.start_listening()

    def is_button_pressed(self, button_name: str) -> bool:
        if button_name not in self.buttons:
            self._xlog.error(f"Button '{button_name}' not defined")
            raise KeyError(f"Button '{button_name}' not defined")

        if self._xconfig.get("gpio.mock", False):
            return self.mocked_buttons_manager.is_button_pressed(pin=self.button_pins_per_name[button_name])

        return self.buttons[button_name].is_pressed

    def _new_button(self, pin: int, mocked_as: str) -> MockedButton:
        if self._xconfig.get("gpio.mock", False):
            self._xlog.warning(f"Creating mocked button for pin {pin} with key binding '{mocked_as}'")
            self.mocked_buttons_manager.add_button(pin=pin, mocked_as=mocked_as)
        else:
            self._xlog.debug(f"Creating real button for pin {pin}")
            from gpiozero import Button

            return Button(pin)
    
    def close(self):
        if self.mocked_buttons_manager is not None:
            self.mocked_buttons_manager.stop_listening()
        

