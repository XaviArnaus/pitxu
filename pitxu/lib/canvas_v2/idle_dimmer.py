import threading

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi


class IdleDimmer(PyXavi):
    """
    Lowers the brightness of the display while the app is idle, and puts it back when it wakes up.

    It only knows the two states and the device (anything with `set_brightness(percent) -> bool`).
    Who decides that the app is idle (the shared memory flag) is the caller's business.

    It needs:
        - params["device"]: the device that sets the brightness.
        - config `dsi_lcd.idle_dimming`: `enabled`, `brightness_percent` (while idle) and `active_percent` (when awake).

    - The level to come back to is configured, never read from the device: if the app died while dimmed,
      reading it at the next start would take the dim level as the normal one.
    - The last requested state always wins, and the same level is not written twice.
    - A failed write is not remembered as done, so the next request tries again.

    Every change goes through `_apply()`, which is where a fade would take place in the future.
    """

    DEFAULT_ENABLED: bool = True
    DEFAULT_DIM_PERCENT: float = 5
    DEFAULT_ACTIVE_PERCENT: float = 100

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config, params: Dictionary):
        super(IdleDimmer, self).init_pyxavi(config=config, params=params)

        if not params.key_exists("device"):
            raise ValueError("'device' parameter is required for IdleDimmer.")
        self._device = params.get("device")

        self._enabled = self._xconfig.get("dsi_lcd.idle_dimming.enabled", self.DEFAULT_ENABLED)
        self._dim_percent = self._xconfig.get("dsi_lcd.idle_dimming.brightness_percent", self.DEFAULT_DIM_PERCENT)
        self._active_percent = self._xconfig.get("dsi_lcd.idle_dimming.active_percent", self.DEFAULT_ACTIVE_PERCENT)

        self._lock = threading.Lock()
        self._applied: float | None = None

        if self._enabled:
            self._xlog.info(f"Idle dimming: {self._dim_percent}% while idle, {self._active_percent}% when awake.")
        else:
            self._xlog.info("Idle dimming is disabled by config.")

    def is_enabled(self) -> bool:
        return bool(self._enabled)

    def dim(self):
        self._apply(self._dim_percent)

    def restore(self):
        self._apply(self._active_percent)

    def _apply(self, percent: float):
        with self._lock:
            if self._applied == percent:
                return
            try:
                if self._device.set_brightness(percent):
                    self._applied = percent
                    self._log_debug(f"Brightness set to {percent}%.")
                else:
                    self._xlog.warning(f"Could not set the brightness to {percent}%.")
            except Exception as e:
                self._xlog.warning(f"Error setting the brightness to {percent}%: {e}")
