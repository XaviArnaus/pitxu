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
                self.buttons[button["name"]] = self._new_button(button["name"], button["pin"], button["mocked_as"])
                self.button_pins_per_name[button["name"]] = button["pin"]
        except (Exception, RuntimeError, SystemExit) as e:
            self._xlog.error(f"Error initializing GPIO buttons: {e}")
            self._xlog.debug(full_stack())
        
        # # Now if the mocked buttons manager exists, start listening
        # if self.mocked_buttons_manager is not None:
        #     self.mocked_buttons_manager.start_listening()
    

    def start_listening(self):
        """
        Start listening to the buttons. This is only needed for mocked buttons,
        as real buttons will trigger callbacks without the need of a listener.
        """
        if self.mocked_buttons_manager is not None:
            self.mocked_buttons_manager.start_listening()
        else:
            self._xlog.debug("Not starting mocked buttons listener, we're not mocked")
    
    def set_pressed_callback(self, button_name: str, callback: callable, kargs: dict = {}):
        if self.is_mocked():
            if self.mocked_buttons_manager.buttons_by_name.get(button_name) is None:
                self._xlog.error(f"Button [{button_name}] not defined in mocked buttons manager")
                raise KeyError(f"Button [{button_name}] not defined in mocked buttons manager")
            
            # We don't have a real button
            def on_press(key):
                if self.mocked_buttons_manager.buttons_by_name.get(button_name) == key:
                    self._xlog.debug(f"Mocked button [{button_name}] was PRESSED, calling callback...")

                    # We set the value to hold the "pressed" state.
                    #   I think this can also be simply the received param `key`
                    mocked_key = self.mocked_buttons_manager.buttons_by_name[button_name]
                    self.mocked_buttons_manager.buttons[mocked_key] = True

                    # Now call the callback
                    callback(key, **kargs)

            # We need to set the callbacks for both press and release, to be able to detect when the button is releasedss
            self.mocked_buttons_manager._on_press = on_press

        else:
            if button_name not in self.buttons or self.buttons[button_name] is None:
                self._xlog.error(f"Button [{button_name}] not defined")
                raise KeyError(f"Button [{button_name}] not defined")

            # We have a real button
            # Feels like it performs the `when_pressed` and inmediately jumps to `when_released`.
            # I'm trying now with `when_held` from 1 sec on.
            # self.buttons[button_name].hold_time = 1
            # self.buttons[button_name].hold_repeat = False
            self.buttons[button_name].when_pressed = lambda: callback(self.buttons[button_name], **kargs)
            # self.buttons[button_name].when_held = lambda: callback(self.buttons[button_name], **kargs)
    
    def set_released_callback(self, button_name: str, callback: callable, kargs: dict = {}):
        if self.is_mocked():
            if self.mocked_buttons_manager.buttons_by_name.get(button_name) is None:
                self._xlog.error(f"Button [{button_name}] not defined in mocked buttons manager")
                raise KeyError(f"Button [{button_name}] not defined in mocked buttons manager")

            # # We don't have a real button
            def on_release(key):
                if self.mocked_buttons_manager.buttons_by_name.get(button_name) == key:
                    self._xlog.debug(f"Mocked button [{button_name}] was RELEASED, calling callback...")

                    # We set the value to hold the "pressed" state.
                    #   I think this can also be simply the received param `key`
                    mocked_key = self.mocked_buttons_manager.buttons_by_name[button_name]
                    self.mocked_buttons_manager.buttons[mocked_key] = False

                    # Now call the callback
                    callback(key, **kargs)

            self.mocked_buttons_manager._on_release = on_release

        else:
            if button_name not in self.buttons or self.buttons[button_name] is None:
                self._xlog.error(f"Button [{button_name}] not defined")
                raise KeyError(f"Button [{button_name}] not defined")

            # We have a real button
            self.buttons[button_name].when_released = lambda: callback(self.buttons[button_name], **kargs)

    def is_pressed(self, button_name: str) -> bool:
        
        if self.is_mocked():
            if self.mocked_buttons_manager.buttons_by_name.get(button_name) is None:
                self._xlog.error(f"Button [{button_name}] not defined in mocked buttons manager")
                raise KeyError(f"Button [{button_name}] not defined in mocked buttons manager")
            
            return self.mocked_buttons_manager.is_pressed(pin=self.button_pins_per_name[button_name])

        else:
            if button_name not in self.buttons or self.buttons[button_name] is None:
                self._xlog.error(f"Button [{button_name}] not defined")
                raise KeyError(f"Button [{button_name}] not defined")

            return self.buttons[button_name].is_pressed

    def _new_button(self, name: str, pin: int, mocked_as: str) -> MockedButton:
        if self.is_mocked():
            self._xlog.warning(f"Creating mocked button [{name}] for pin [{pin}] with key binding [{mocked_as}]")
            self.mocked_buttons_manager.add_button(name=name, pin=pin, mocked_as=mocked_as)
        else:
            self._xlog.debug(f"Creating real button [{name}] for pin [{pin}]")
            from gpiozero import Button

            return Button(pin, pull_up=False)
            # return Button(pin, pull_up=True)
    
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
    # This is per key, not per name.
    buttons: dict = {}
    buttons_by_pin: dict = {}
    buttons_by_name: dict = {}
    _listener = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(MockedButtons, self).init_pyxavi(config=config, params=params)
        self.buttons = {}
    
    def add_button(self, name: str, pin: int, mocked_as: str):

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

        # Yet another useless mapp.
        self.buttons_by_name[name] = mocked_key

    def is_pressed(self, pin: int) -> bool:
        if str(pin) not in self.buttons_by_pin or self.buttons_by_pin[str(pin)] is None:
            self._xlog.error(f"Button with pin '{pin}' not defined in mocked buttons")
            raise KeyError(f"Button with pin '{pin}' not defined in mocked buttons")

        key = self.buttons_by_pin[str(pin)]
        value = self.buttons[key]
        return value
    
    def _on_press(self, key: str):
        # Be aware that this method is never called, as we place callbacks replacing it.
        if key in self.buttons:
            self._xlog.debug(f"Mocking GPIO: {key} key was PRESSED")
            self.buttons[key] = True
    
    def _on_release(self, key: str):
        # Be aware that this method is never called, as we place callbacks replacing it.
        if key in self.buttons:
            self._xlog.debug(f"Mocking GPIO: {key} key was RELEASED")
            self.buttons[key] = False
    
    def start_listening(self):
        from pynput.keyboard import Listener

        self._listener = Listener(on_press=self._on_press, on_release=self._on_release, args=())
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
