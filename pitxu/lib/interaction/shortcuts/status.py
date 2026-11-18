from pyxavi import Config, Dictionary
from pitxu.lib.objects import XprocAction
from pitxu.lib.interaction.shortcuts.shortcut_base import ShortcutBase

from definitions import QUEUE_DSI_LCD

class Status(ShortcutBase):
    """
    Shortcuts to send interactions to the status display
    """

    # The idea is to keep a short history of entries, and when it's full, the oldest one is removed.
    # Each entry is a (text, color) tuple. The text starts with an icon, the display wraps the
    #   text keeping the icon's width as hanging indent. The display then shows only the newest
    #   entries that fit in its area, so this is just the buffer size.
    status_lines: list[tuple[str, any]] = []
    how_many_status_lines_to_keep: int = 12

    # The startup screen ("Ready") stays in the area until something else is painted there.
    # It is pending to be cleared from the moment the startup paints it, until a status line, or a clear, takes its place.
    # ⚠️ It must NOT be pending by default: status lines can be added before the startup paints
    #   (the monitor fires some at boot), and then the startup screen is painted over them.
    startup_screen_pending: bool = False

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Status, self).__init__(config=config, params=params)

        self._xlog.info("Initializing Status interaction shortcuts.")

    # --------- (Proxy) Functions to trigger interactions ---------

    def add_new_status_line(self, text: str, color: str | tuple | int = None):
        """
        Adds a new status line on the status display.

        It also maintains the list of status lines, and when the list is full, it removes the oldest one.

        Args:
            text (str): The text to show in the status line. It should start with an icon.
            color (str | tuple | int): The color of this line. None for the default one.
                It can be a Canvas color name (like "red"), or a Canvas color value (like canvas.COLOR_RED).
        """
        # This paint replaces whatever the startup left in the area.
        self.startup_screen_pending = False

        # Maintain the list of status lines.
        self.status_lines.append((text, color))
        if len(self.status_lines) > self.how_many_status_lines_to_keep:
            self.status_lines.pop(0)

        self.process_pool.send(self.get_queue(), XprocAction.STATUS_LINE, {
            # The full history to draw, and the last one separately for logging
            "entries": list(self.status_lines),
            "added": (text, color)
        })

    # --------- (Proxy) Functions to clear screens ---------

    def mark_startup_screen_shown(self):
        """
        The startup paints its screens over the status area: from now on it has to be cleared at the first interaction.
        """
        self.startup_screen_pending = True

    def clear_startup_screen(self):
        """
        Clears the startup screen ("Ready") from the status area, leaving it empty.
        It does it only once, and only if no status line has replaced it already.
        Meant to be called when the user does the first interaction.
        """
        if not self.startup_screen_pending:
            return
        self.startup_screen_pending = False
        self._xlog.debug("🧹 Clearing the startup screen from the status area.")
        self.soft_clear()

    def soft_clear(self):
        self.process_pool.send(self.get_queue(), XprocAction.STATUS_CLEAR)
    
    def clear_device(self):
        """
        Clear the display device, the hard way.
        """
        self._xlog.debug("🧹 Clearing the display device.")

        self.process_pool.send(QUEUE_DSI_LCD, XprocAction.CLEAR)
        
