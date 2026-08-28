from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.core.xprocess_pool import XprocessPool
from pitxu.lib.objects import XprocAction
from pitxu.lib.interaction.shortcuts.shortcut_base import ShortcutBase

from definitions import QUEUE_SPEAKER, QUEUE_EINK, QUEUE_MATRIX, QUEUE_LCD, QUEUE_DSI_LCD, QUEUE_SUPPORT, \
                        SHARED_SPEAKER_BUSY, SHARED_NETWORK_BUSY, SHARED_VAD_DETECTED, \
                        SHARED_MICROPHONE_MUTED, SHARED_CHATBOT_BUSY, SHARED_CHATBOT_ANSWER_IS_ERROR, SHARED_MATRIX_BUSY, SHARED_DSI_LCD_BUSY,\
                        SHARED_DSI_LCD_IDLE_MODE, SHARED_SUPPORT_BUSY, SHARED_STT_BUSY, SHARED_TRANSCRIBER_BUSY

class Background(ShortcutBase):
    """
    Shortcuts to send interactions to the background display
    """
    
    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Background, self).__init__(config=config, params=params)

        self._xlog.info("Initializing Background interaction shortcuts.")
    
    # --------- (Proxy) Functions to trigger interactions ---------
    
    def show_thinking(self):
        """
        Triggers a "thinking" interaction on the background display.

        This needs the SHARED_CHATBOT_BUSY flag to be set by the Chatbot/Main process.
        TODO: this is a clear candidate to the BusyFlagsManager automatic handling.
        """

        self._log_debug("🤖 Triggering thinking interaction on background display.")

        self.process_pool.send(self.get_queue(), XprocAction.THINKING)
    
    def show_networking(self):
        """
        Triggers a "networking" interaction on the background display.

        This needs the SHARED_NETWORK_BUSY flag to be set by the Communication/Main process.
        TODO: this is a clear candidate to the BusyFlagsManager automatic handling.
        """

        self._log_debug("🤖 Triggering networking interaction on background display.")

        self.process_pool.send(self.get_queue(), XprocAction.NETWORKING)
    
    def show_interaction_holding_percentage(self, percentage: int):
        """
        Shows the interaction holding percentage on the background display.

        Args:
            percentage (int): The percentage of time left for the interaction.
        """
        self._log_debug(f"🚥 Showing interaction holding percentage {percentage}% on background display")
        self.process_pool.send(self.get_queue(), XprocAction.INTERACTION_HOLDING_PERCENTAGE, percentage)


    # --------- (Proxy) Functions to clear screens ---------

    def soft_clear(self):
        self.process_pool.send(self.get_queue(), XprocAction.BACKGROUND_CLEAR)
    
    def clear_device(self):
        """
        Clear the display device, the hard way.
        """
        self._xlog.debug("🧹 Clearing the display device.")

        self.process_pool.send(QUEUE_DSI_LCD, XprocAction.CLEAR)
        
