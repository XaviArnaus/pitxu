from __future__ import annotations
from pyxavi import Config, Dictionary, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi

class Buttons(PyXavi):

    mocked_buttons_manager: MockedButtons = None
    buttons: dict[str, MockedButton] = {}
    button_pins_per_name: dict[str, int] = {}

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Buttons, self).init_pyxavi(config=config, params=params)

    def initialize_buttons(self):
        # Initialise GPIO buttons
        self._xlog.info("Initialising GPIO buttons...")

        # First of all, in case we are mocked, initialize the singleton that manages the buttons
        if self.is_mocked():
            self._xlog.warning("Using mocked GPIO buttons")
            self.mocked_buttons_manager = MockedButtons(config=self._xconfig, params=self._xparams)

        # Gather the definitions from the config and initialise them
        try:
            button_definitions = self._xconfig.get("gpio.buttons.devices", [])
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
        if button_name not in self.buttons or self.buttons[button_name] is None:
            self._xlog.error(f"Button '{button_name}' not defined")
            raise KeyError(f"Button '{button_name}' not defined")

        if self.is_mocked():
            return self.mocked_buttons_manager.is_button_pressed(pin=self.button_pins_per_name[button_name])

        return self.buttons[button_name].is_pressed

    def _new_button(self, pin: int, mocked_as: str) -> MockedButton:
        if self.is_mocked():
            self._xlog.warning(f"Creating mocked button for pin {pin} with key binding '{mocked_as}'")
            self.mocked_buttons_manager.add_button(pin=pin, mocked_as=mocked_as)
        else:
            self._xlog.debug(f"Creating real button for pin {pin}")
            from gpiozero import Button

            return Button(pin)
    
    def close(self):
        if self.mocked_buttons_manager is not None:
            self.mocked_buttons_manager.stop_listening()
    
    def is_mocked(self) -> bool:
        return self._xconfig.get("gpio.mock", False) and self._xconfig.get("gpio.buttons.mock", False)


class MockedButtons(PyXavi):
    """
    Mocking gpiozero.Button for testing purposes.
    This aims to have a single mocking instance with all mocked buttons defined.
    This way we intend to reduce the number of keyboard listeners created.
    This change from having one listener per button to a single listener for all buttons
    fixed the Mac OS issue where more than 2 key listeners provoked "Abort trap: 6" errors.
    """
    buttons: dict = {}
    buttons_by_pin: dict = {}
    _listener = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(MockedButtons, self).init_pyxavi(config=config, params=params)
        self.buttons = {}
    
    def add_button(self, pin: int, mocked_as: str):

        from pynput.keyboard import Key

        # Initially, accepting what it comes
        mocked_key = mocked_as

        # Now we go through our known special keys
        if mocked_as == "space":
            mocked_key = Key.space
        elif mocked_as == "enter":
            mocked_key = Key.enter
        elif mocked_as == "esc":
            mocked_key = Key.esc
        elif mocked_as == "tab":
            mocked_key = Key.tab
        elif mocked_as == "shift":
            mocked_key = Key.shift
        elif mocked_as == "ctrl":
            mocked_key = Key.ctrl

        # The value is the initial state of the button (not pressed)
        self.buttons[mocked_key] = False

        # Now we fill the reverse mapping
        self.buttons_by_pin[str(pin)] = mocked_key

    def is_button_pressed(self, pin: int) -> bool:
        if str(pin) not in self.buttons_by_pin or self.buttons_by_pin[str(pin)] is None:
            self._xlog.error(f"Button with pin '{pin}' not defined in mocked buttons")
            raise KeyError(f"Button with pin '{pin}' not defined in mocked buttons")

        key = self.buttons_by_pin[str(pin)]
        value = self.buttons[key]
        return value
    
    def _on_press(self, key):
        if key in self.buttons:
            self._xlog.debug(f"Mocking GPIO: {key} key was PRESSED")
            self.buttons[key] = True
    
    def _on_release(self, key):
        if key in self.buttons:
            self._xlog.debug(f"Mocking GPIO: {key} key was RELEASED")
            self.buttons[key] = False
    
    def start_listening(self):
        from pynput.keyboard import Listener

        self._listener = Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.start()

    def stop_listening(self):
        if self._listener is not None:
            self._listener.stop()

class MockedButton(PyXavi):
    """
    Mocked version of gpiozero.Button for testing purposes.
    """

    @property
    def is_pressed(self) -> bool:
        pass
