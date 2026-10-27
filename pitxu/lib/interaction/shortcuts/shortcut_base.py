from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.core.xprocess_pool import XprocessPool
from pitxu.lib.objects import XprocAction

from pitxu.lib.text_to_speech.piper import Piper
from pitxu.lib.text_to_speech.text_to_speech import TextToSpeech
from pitxu.lib.eink.display import Display as eInk
from pitxu.lib.matrix_led import MatrixLed
from pitxu.lib.lcd.lcd import Lcd
from pitxu.lib.dsi_lcd.dsi_lcd import DsiLcd
from pitxu.lib.utils.text import Text

from sounddevice import RawInputStream
from multiprocessing import JoinableQueue

from definitions import QUEUE_SPEAKER, QUEUE_EINK, QUEUE_MATRIX, QUEUE_LCD, QUEUE_DSI_LCD, QUEUE_SUPPORT, \
                        SHARED_SPEAKER_BUSY, SHARED_NETWORK_BUSY, SHARED_VAD_DETECTED, \
                        SHARED_MICROPHONE_MUTED, SHARED_CHATBOT_BUSY, SHARED_CHATBOT_ANSWER_IS_ERROR, SHARED_MATRIX_BUSY, SHARED_DSI_LCD_BUSY,\
                        SHARED_DSI_LCD_IDLE_MODE, SHARED_SUPPORT_BUSY, SHARED_STT_BUSY, SHARED_TRANSCRIBER_BUSY

class ShortcutBase(PyXavi):

    display_queue: str = None

    # Subprocess control
    process_pool: XprocessPool = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(ShortcutBase, self).init_pyxavi(config=config, params=params)

        self._xlog.info("Initializing Foreground interaction shortcuts.")

        # All interactions will be done via processes
        if params.key_exists("process_pool"):
            self.process_pool = params.get("process_pool")
        else:
            raise ValueError("Missing 'process_pool' parameter")
        
        # Important to get the display_queue
        if params.key_exists("display_queue"):
            self.display_queue = params.get("display_queue")
        else:
            raise ValueError("Missing 'display_queue' parameter")
    
    def close(self):
        """
        Close the Background interaction shortcuts.
        """
        self._xlog.debug("Closing Background interaction shortcuts.")

        self.process_pool.get_memory_manager().force_all_flags_to_idle(is_closing=True)
    
    # --------- Helper functions ---------

    def get_queue(self):
        """
        Get the active background display queue.

        Returns:
            str: The queue name of the active background display.
        """
        return self.display_queue
    
    def get_display_busy_flag(self):
        """
        Get the active background display busy flag.

        Returns:
            str: The busy flag name of the active background display.
        """
        return self.process_pool.get_busy_flag_from_related_queue(self.get_queue())