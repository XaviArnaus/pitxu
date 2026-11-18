from __future__ import annotations
import os
import sys
import threading
import time
from pyxavi import Config, Dictionary, full_stack
from pitxu.lib.abstract.pyxavi import PyXavi

class Buttons(PyXavi):

    mocked_buttons_manager: MockedButtons = None
    buttons: dict[str, MockedButton] = {}
    button_pins_per_name: dict[str, int] = {}

    # Real buttons: how long the poll waits for the gpiozero event of a press it noticed, before covering it.
    POLL_GRACE_SECONDS: float = 0.15
    # Real buttons: an event of gpiozero that arrives this soon after the poll covered it is the same press.
    POLL_DEDUPE_SECONDS: float = 0.5

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Buttons, self).init_pyxavi(config=config, params=params)
        # The callbacks of the real buttons: {button name: {"PRESSED"/"RELEASED": (callback, kargs)}}
        self._callbacks: dict[str, dict[str, tuple]] = {}
        # When (monotonic) gpiozero delivered an event, and the poll covered one, per (button name, event).
        self._last_event_at: dict[tuple[str, str], float] = {}
        self._last_fallback_at: dict[tuple[str, str], float] = {}
        self._fallback_warned: bool = False
        # How many presses/releases the poll had to cover in this run, and who to tell about each (see set_fallback_notifier).
        self._fallback_count: int = 0
        self._fallback_notifier: callable | None = None
        self._pollers: dict[str, threading.Thread] = {}
        self._poll_stop = threading.Event()

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
                if not self.is_mocked():
                    self._ensure_poller(button["name"])
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
            self._xlog.debug("Not starting mocked buttons listener: we're not mocked")
    
    def get_buttons(self) -> dict[str, MockedButton]:
        """"
        Get the buttons dictionary.
        """
        return self.buttons
    
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
            # TODO: The conclusions of the test are in `self.is_pressed` method.
            # self.buttons[button_name].hold_time = 1
            # self.buttons[button_name].hold_repeat = False
            self.buttons[button_name].when_pressed = self._logged_callback(button_name, "PRESSED", callback, kargs)
            # self.buttons[button_name].when_pressed = None
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
            self.buttons[button_name].when_released = self._logged_callback(button_name, "RELEASED", callback, kargs)

    def _logged_callback(self, button_name: str, event: str, callback: callable, kargs: dict) -> callable:
        """
        Wraps the callback of a real button so that the app log shows that the event arrived, and what went wrong if
        the callback failed. gpiozero runs the callbacks in its own thread, where an exception is not logged
        by us, just printed to stderr: without this, a failing callback looks like a button that does nothing.
        """
        key = (button_name, event)
        # The poll fallback calls the same callback when this event does not arrive.
        self._callbacks.setdefault(button_name, {})[event] = (callback, kargs)

        def on_event():
            now = time.monotonic()
            self._last_event_at[key] = now
            if now - self._last_fallback_at.get(key, -1e9) < self.POLL_DEDUPE_SECONDS:
                self._xlog.debug(f"🕹️ Button [{button_name}] {event} (gpiozero event) arrived late: the poll fallback already handled it.")
                return
            self._dispatch(button_name, event, "gpiozero event")
        return on_event

    def _dispatch(self, button_name: str, event: str, source: str):
        """ Calls the callback of a real button, logging what went wrong: its thread does not log exceptions. """
        callback, kargs = self._callbacks[button_name][event]
        self._xlog.debug(f"🕹️ Button [{button_name}] {event} ({source}), calling its callback.")
        try:
            callback(self.buttons[button_name], **kargs)
        except Exception as e:
            self._xlog.error(f"🛑 The callback of the button [{button_name}] {event} failed: {type(e).__name__}: {e}")
            self._xlog.debug(full_stack())

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
        
            # The following `is_held` does not improve. During the 1 sec of hold_time, the button is still considered "pressed".
            #   but returns RELEASED because the hold_time is still "running".
            # What I want to achieve is only a single call to the callback.
            #return self.buttons[button_name].is_held

    def _new_button(self, name: str, pin: int, mocked_as: str) -> MockedButton:
        if self.is_mocked():
            self._xlog.warning(f"Creating mocked button [{name}] for pin [{pin}] with key binding [{mocked_as}]")
            self.mocked_buttons_manager.add_button(name=name, pin=pin, mocked_as=mocked_as)
        else:
            self._xlog.debug(f"Creating real button [{name}] for pin [{pin}]")
            from gpiozero import Button, Device

            # return Button(pin, pull_up=False)
            button = Button(pin, pull_up=True)
            # Which pin factory gpiozero ended up with decides if the events ever arrive (on a Pi 5 only the lgpio ones can read the pins).
            self._xlog.debug(
                f"Button [{name}] on pin [{pin}] created with the pin factory "
                f"[{type(Device.pin_factory).__name__}], pressed right now: {button.is_pressed}")
            # The same app behaves differently as a service and in the foreground (a different environment): this is
            # what to compare between both logs.
            try:
                self._xlog.debug(
                    f"Button process context: pid={os.getpid()} uid={os.getuid()} groups={os.getgroups()} cwd={os.getcwd()} "
                    f"tty={sys.stdin.isatty() if sys.stdin else None} "
                    f"LG_WD={os.environ.get('LG_WD')} GPIOZERO_PIN_FACTORY={os.environ.get('GPIOZERO_PIN_FACTORY')}")
            except Exception as e:
                self._xlog.debug(f"Could not describe the button process context: {e}")
            return button

    def _ensure_poller(self, name: str):
        """
        Starts the thread that reads the pin of a real button itself (once per button), for:
            - The fallback (gpio.buttons.poll_fallback): on some starts the gpiozero events never arrive, while
              the pin reads fine. A press that the poll notices and that gets no event is handled by the poll.
            - The diagnosis (gpio.buttons.debug_state_log): logs every change of the pin state.
        """
        fallback = bool(self._xconfig.get("gpio.buttons.poll_fallback.enabled", True))
        debug = bool(self._xconfig.get("gpio.buttons.debug_state_log", False))
        if not (fallback or debug) or name in self._pollers:
            return
        interval = max(0.01, float(self._xconfig.get("gpio.buttons.poll_fallback.interval_seconds", 0.05)))
        self._xlog.debug(f"Button [{name}] poll thread: fallback {fallback}, state log {debug}, every {interval}s")
        thread = threading.Thread(
            name=f"ButtonPoller-{name}", target=self._poll_button, args=(name, fallback, debug, interval), daemon=True)
        self._pollers[name] = thread
        thread.start()

    def _poll_button(self, name: str, fallback: bool, debug: bool, interval: float):
        button = self.buttons[name]
        try:
            last = button.is_pressed
        except Exception as e:
            self._xlog.error(f"🕹️ Could not read the button [{name}] to poll it: {e}")
            return
        while not self._poll_stop.wait(interval):
            try:
                current = button.is_pressed
            except Exception as e:
                if not self._poll_stop.is_set():
                    self._xlog.error(f"🕹️ Could not read the button [{name}] to poll it: {e}")
                return
            if current == last:
                continue
            last = current
            event = "PRESSED" if current else "RELEASED"
            if debug:
                self._xlog.info(f"🕹️ [BUTTON DEBUG] Button [{name}] state read as {event}")
            if fallback and event in self._callbacks.get(name, {}):
                self._cover_if_missing(name, event, interval)

    def _cover_if_missing(self, name: str, event: str, interval: float):
        """
        The poll saw the pin change: if gpiozero does not deliver its event for it, the poll calls the callback.
        """
        noticed_at = time.monotonic()
        # The event normally arrives within milliseconds, sometimes just before the poll noticed.
        if self._poll_stop.wait(self.POLL_GRACE_SECONDS):
            return
        key = (name, event)
        if self._last_event_at.get(key, 0.0) >= noticed_at - interval - 0.05:
            return
        self._last_fallback_at[key] = time.monotonic()
        self._fallback_count += 1
        if not self._fallback_warned:
            self._fallback_warned = True
            self._xlog.warning(
                f"🕹️ The gpiozero events of the button [{name}] are not arriving: the poll fallback is covering them "
                f"(gpio.buttons.poll_fallback).")
        self._xlog.info(f"🕹️ Button [{name}] {event} covered by the poll fallback (#{self._fallback_count} in this run).")
        if self._fallback_notifier is not None and self._xconfig.get("gpio.buttons.poll_fallback.show_status_line", True):
            try:
                self._fallback_notifier(self._fallback_count, name, event)
            except Exception as e:
                self._xlog.error(f"🛑 Could not notify that the poll fallback covered the button [{name}] {event}: {e}")
        self._dispatch(name, event, "poll fallback")

    def set_fallback_notifier(self, notifier: callable):
        """
        Registers who is told each time the poll fallback has to cover an event that gpiozero did not deliver:
        notifier(count_in_this_run, button_name, event). It runs in the poll thread.
        """
        self._fallback_notifier = notifier

    def close(self):
        self._poll_stop.set()
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
