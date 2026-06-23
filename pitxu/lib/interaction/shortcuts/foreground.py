from pyxavi import Config, Dictionary, dd

from pitxu.lib.objects import XprocAction
from pitxu.lib.interaction.shortcuts.shortcut_base import ShortcutBase

from definitions import QUEUE_EINK, QUEUE_DSI_LCD, SHARED_DSI_LCD_BUSY,\
                        SHARED_DSI_LCD_IDLE_MODE

class Foreground(ShortcutBase):
    """
    Shortcuts to send interactions to the foreground display
    """
    
    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Foreground, self).__init__(config=config, params=params)

        self._xlog.info("Initializing Foreground interaction shortcuts.")
 
    
    def close(self):
        """
        Close the Foreground interaction shortcuts.
        """
        self._xlog.debug("Closing Foreground interaction shortcuts.")

        self.process_pool.get_memory_manager().force_all_flags_to_idle(is_closing=True)
    
    # --------- (Proxy) Functions to trigger interactions ---------
    
    def show_startup(self):
        """
        Show the startup splash screen on the Foreground display.
        """
        self.process_pool.send(self.get_queue(), XprocAction.STARTUP)
    
    def show_error(self, text: str, for_seconds: float = 3.0):
        """
        Show the error screen on the Foreground display.
        """
        self.process_pool.send(self.get_queue(), XprocAction.SHOW_ERROR, {
            "text": text,
            "for_seconds": for_seconds
        })

    def show_init_phases(self, step: int, text: str = None):
        """
        Show the initialization phases on the Foreground display.
        """
        self.process_pool.send(self.get_queue(), XprocAction.STARTUP_WITH_PHASE, param={
            "phase": step,
            "text": text
        })

    def show_idle(self):
        """
        Show the idle mode on the Foreground display.
        """
        self._xlog.debug("👀 Starting idle mode from Interaction class")
        self.process_pool.send(self.get_queue(), XprocAction.SHOW_IDLE)
        self.process_pool.wait_for_queue_to_empty(self.get_queue())
        self.process_pool.get_memory_manager().wait_for_busy_process_to_idle(SHARED_DSI_LCD_BUSY)
        self.process_pool.get_memory_manager().write_shared_memory_flag(SHARED_DSI_LCD_IDLE_MODE, True)
    
    def show_arbitrary_text_on_foreground(
            self,
            icon: str = None,
            text: str = None,
            font_size: int = 24,
            header: str = None,
            font_header_size: int = 32,
            padding = 5,
            show_for_seconds = None
        ):
        """
        Shows arbitrary text on the foreground display.
        """
        self.process_pool.send(self.get_queue(), XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND, {
            "icon": icon,
            "text": text,
            "font_size": font_size,
            "header": header,
            "font_header_size": font_header_size,
            "padding": padding,
            "show_for_seconds": show_for_seconds
        })
    
    def show_arbitrary_text_on_foreground_while_idle(
            self,
            icon: str = None,
            text: str = None,
            font_size: int = 24,
            header: str = None,
            font_header_size: int = 32,
            padding = 5,
            show_for_seconds = None
        ):
        """
        Shows arbitrary text on the foreground display.
        """
        self.process_pool.send(self.get_queue(), XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND_IDLE, {
            "icon": icon,
            "text": text,
            "font_size": font_size,
            "header": header,
            "font_header_size": font_header_size,
            "padding": padding,
            "show_for_seconds": show_for_seconds
        })
    
    def show_arbitrary_icon_on_foreground(
            self,
            icon: str = None,
            text: str = None,
            color: str = None
        ):
        """
        Shows arbitrary icon on the foreground display.
        """
        self.process_pool.send(self.get_queue(), XprocAction.SHOW_ARBITRARY_ICON_FOREGROUND, {
            "icon": icon,
            "text": text,
            "color": color
        })

    def show_arbitrary_text_on_foreground_while_speaking(
            self,
            icon: str = None,
            text: str = None,
            font_size: int = 24,
            header: str = None,
            font_header_size: int = 32,
            padding = 5
        ):
        """
        Shows arbitrary text on the foreground display only while speaking.
        """
        self.process_pool.send(self.get_queue(), XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND_SPEAKING, {
            "icon": icon,
            "text": text,
            "font_size": font_size,
            "header": header,
            "font_header_size": font_header_size,
            "padding": padding
        })
    
    def show_arbitrary_icon_on_foreground_while_user_speaking(
            self,
            icon: str = None,
            text: str = None,
            color: str = None
        ):
        """
        Shows arbitrary icon on the foreground display only while the user is speaking.
        """
        self.process_pool.send(self.get_queue(), XprocAction.SHOW_ARBITRARY_ICON_FOREGROUND_USER_SPEAKING, {
            "icon": icon,
            "text": text,
            "color": color
        })
    
    def show_arbitrary_text_on_foreground_while_thinking(
            self,
            icon: str = None,
            text: str = None,
            font_size: int = 24,
            header: str = None,
            font_header_size: int = 32,
            padding = 5
        ):
        """
        Shows arbitrary text on the foreground display only while thinking.
        """
        self.process_pool.send(self.get_queue(), XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND_THINKING, {
            "icon": icon,
            "text": text,
            "font_size": font_size,
            "header": header,
            "font_header_size": font_header_size,
            "padding": padding
        })
    
    def show_arbitrary_text_on_foreground_while_networking(
            self,
            icon: str = None,
            text: str = None,
            font_size: int = 24,
            header: str = None,
            font_header_size: int = 32,
            padding = 5
        ):
        """
        Shows arbitrary text on the foreground display only while networking.
        """
        self.process_pool.send(self.get_queue(), XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND_NETWORKING, {
            "icon": icon,
            "text": text,
            "font_size": font_size,
            "header": header,
            "font_header_size": font_header_size,
            "padding": padding
        })
    
    def show_code_block_on_foreground(self, code: str, for_seconds: float = 10.0):
        """
        Shows a code block on the foreground display.

        Args:
            code (str): The code block to show.
        """
        self.process_pool.send(self.get_queue(), XprocAction.SHOW_CODE_BLOCK, {
            "code": code,
            "for_seconds": for_seconds
        })
    
    def show_code_block_on_foreground_while_speaking(self, code: str, for_seconds: float = 10.0):
        """
        Shows a code block on the foreground display while speaking.

        Args:
            code (str): The code block to show.
        """
        self.process_pool.send(self.get_queue(), XprocAction.SHOW_CODE_BLOCK_WHILE_SPEAKING, {
            "code": code,
            # This is not used, but I'd like that stays AT MINIMUM for_seconds,
            #   even after finishing speaking.
            "for_seconds": for_seconds
        })
    
    def show_text_block_on_foreground(self, text: str, for_seconds: float = 10.0):
        """
        Shows a text block on the foreground display.

        Args:
            text (str): The text block to show.
        """
        self.process_pool.send(self.get_queue(), XprocAction.SHOW_TEXT_BLOCK, {
            "text": text,
            "for_seconds": for_seconds
        })
    
    def show_text_block_on_foreground_while_speaking(self, text: str, for_seconds: float = 10.0):
        """
        Shows a text block on the foreground display while speaking.

        Args:
            text (str): The text block to show.
        """
        self.process_pool.send(self.get_queue(), XprocAction.SHOW_TEXT_BLOCK_WHILE_SPEAKING, {
            "text": text,
            # This is not used, but I'd like that stays AT MINIMUM for_seconds,
            #   even after finishing speaking.
            "for_seconds": for_seconds
        })

    # --------- (Proxy) Functions to clear screens ---------

    def soft_clear(self):
        # Only for eInk: Hard Clear is slow. As we can use partial refresh, we do a soft clear first.
        if self._get_active_foreground_display_queue() == QUEUE_EINK:
            # First a soft clear, so the screen is white
            self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.SOFT_CLEAR)

        # Full clear, to ensure a reset.
        # self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.CLEAR)
        self.process_pool.send(self._get_active_foreground_display_queue(), XprocAction.FOREGROUND_CLEAR)
    
    def clear_device(self):
        """
        Clear the display device, the hard way.
        """
        self._xlog.debug("🧹 Clearing the display device.")

        self.process_pool.send(QUEUE_DSI_LCD, XprocAction.CLEAR)