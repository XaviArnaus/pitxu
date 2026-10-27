from pyxavi import Config, Dictionary, dd
from pitxu.lib.objects import XprocAction
from pitxu.lib.interaction.shortcuts.shortcut_base import ShortcutBase

from definitions import QUEUE_DSI_LCD

class Status(ShortcutBase):
    """
    Shortcuts to send interactions to the status display
    """

    # The idea is to keep a bunch of them, and when it's full, the oldest one is removed.
    status_lines: list[str] = []
    how_many_status_lines_to_show: int = 9
    
    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Status, self).__init__(config=config, params=params)

        self._xlog.info("Initializing Status interaction shortcuts.")
    
    # --------- (Proxy) Functions to trigger interactions ---------
    
    def add_new_status_line(self, text: str, color: str = None):
        """
        Adds a new status line on the status display.

        It also maintains the list of status lines, and when the list is full, it removes the oldest one.

        Args:
            text (str): The text to show in the status line.
            color (str): The color of the text in the status line.
        """
        # Maintain the list of status lines.
        self.status_lines.append(text)
        if len(self.status_lines) > self.how_many_status_lines_to_show:
            self.status_lines.pop(0)

        self.process_pool.send(self.get_queue(), XprocAction.STATUS_LINE, {
            "text": "\n".join(self.status_lines),
            "color": color
        })

    # --------- (Proxy) Functions to clear screens ---------

    def soft_clear(self):
        self.process_pool.send(self.get_queue(), XprocAction.STATUS_CLEAR)
    
    def clear_device(self):
        """
        Clear the display device, the hard way.
        """
        self._xlog.debug("🧹 Clearing the display device.")

        self.process_pool.send(QUEUE_DSI_LCD, XprocAction.CLEAR)
        
