from __future__ import annotations
from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi

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
        if str(pin) not in self.buttons_by_pin:
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