import time

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.objects.communication import ArbitraryText, ChatbotAnswer, StatusUpdate, StatusType, ArbitraryContent

from pitxu.lib.objects.xproc_action import XprocAction
from pitxu.lib.utils.xprocess_pool import XprocessPool
from pitxu.lib.eink import Display
from pitxu.lib.matrix_led import MatrixLed
from pitxu.lib.text_to_speech import Piper

from definitions import QUEUE_EINK, QUEUE_MATRIX, QUEUE_SPEAKER, SHARED_SPEAKER_BUSY, SHARED_EINK_IDLE_MODE

class Interaction(PyXavi):

    EINK = "eink"
    MATRIX_LED = "matrix_led"
    ST7789P3 = "st7789p3"

    displays_config: dict = None
    displays_map = {
        EINK: Display,
        MATRIX_LED: MatrixLed,
        # ST7789P3: ST7789P3
    }
    displays_that_need_initial_clear = [MATRIX_LED]
    displays_in_use = []

    

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Interaction, self).init_pyxavi(config=config, params=params)

        self.displays_config = self._xconfig.get("displays", default={
            "merge_displays": False,
            "unmerged_displays": {
                "notification_display": self.EINK,
                "status_display": self.MATRIX_LED
            },
            "merged_display": {
                "main_display": self.ST7789P3
            }
        })
    
    def initialize(self):
        # The hardware for interaction lives in separate processes

        # Process Pool (initialisation of process handling)
        self._process_pool = XprocessPool(config=self._xconfig, params=self._xparams)

        device_initialization = []

        if self.displays_config.get("merge_displays"):
            for device_name in self.displays_config.get("merged_display", {}).values():
                if device_name in self.displays_map:
                    device_initialization.append((device_name, self.displays_map[device_name]))
        elif not self.displays_config.get("merge_displays", False):
            for device_name in self.displays_config.get("unmerged_displays", {}).values():
                if device_name in self.displays_map:
                    device_initialization.append((device_name, self.displays_map[device_name]))
        
        self.displays_in_use = [device_name for device_name, _ in device_initialization]

        for device_name, device_class in device_initialization:
            self._xlog.info(f"Initialising {device_name} Display and Macros")
            self._process_pool.new_and_start(QUEUE_EINK, target=device_class)

        # Does any of the devices need an initial clear?
        for device_name, _ in device_initialization:
            if device_name in self.displays_that_need_initial_clear:
                self.clear(which_one=device_name)

        # Initialise Text-To-Speech.
        self._xlog.debug("Initialising the Text-to-Speech with language [" + self._xparams.get("language") + "]")
        self._process_pool.new_and_start(QUEUE_SPEAKER, target=Piper)

    def communicate(self, communication: ArbitraryText | ChatbotAnswer | StatusUpdate | ArbitraryContent):
        if isinstance(communication, ChatbotAnswer):
            # This is intended for answers from the chatbot.
            return self.handle_chatbot_answer(communication)
        elif isinstance(communication, StatusUpdate):
            # This is intended for INIT_PHASE, HOLDING_INTERACTION and THINKING updates.
            return self.handle_status_update(communication)
        elif isinstance(communication, ArbitraryContent):
            # This is intended for arbitrary content like coming from function callbacks.
            return self.handle_arbitrary_content(communication)
        elif isinstance(communication, ArbitraryText):
            # This is intended for arbitrary text to be spoken/displayed, like the Greetings and Farewells.
            return self.handle_arbitrary_text(communication)
        else:
            self._xlog.error(f"Unknown communication type: {type(communication)}")
            return None
    
    def show_idle(self):
        self._xlog.debug("👀 Starting eInk idle mode from Interaction")
        self._process_pool.get_memory_manager().write_shared_memory_flag(SHARED_EINK_IDLE_MODE, True)
        self._process_pool.send(QUEUE_EINK, XprocAction.SHOW_IDLE_EINK)

    def clear(self,
              all: bool = False,
              which_one: str = None):
        
        # If we don't say anything, clear all
        if not all and which_one is None:
            all = True

        # do we relate to EINK?
        if (all or which_one == self.EINK) and \
            self.displays_in_use.count(self.EINK) > 0:

            self._xlog.debug("Clearing EINK")
            # First a soft clear, so the screen is white
            self._process_pool.send(QUEUE_EINK, XprocAction.SOFT_CLEAR)
            # Full clear, to ensure a reset.
            self._process_pool.send(QUEUE_EINK, XprocAction.CLEAR)

        # do we relate to MATRIX_LED?
        if (all or which_one == self.MATRIX_LED) and \
            self.displays_in_use.count(self.MATRIX_LED) > 0:

            self._xlog.debug("Clearing MATRIX_LED")
            self._process_pool.send(QUEUE_MATRIX, XprocAction.LED_CLEAR)
        
        # It is not yet created
        # if (all or merged_display) and \
        #     self.displays_config.get("merge_displays", True) and \
        #     self.displays_config.get("merged_display", None).get("main_display", None) == "st7789p3":

        #     # self._xlog.debug("Clearing merged display")
        #     # self._process_pool.send(QUEUE_EINK, XprocAction.EINK_CLEAR)
        #     # self._process_pool.send(QUEUE_MATRIX, XprocAction.LED_CLEAR)
    
    def handle_arbitrary_text(self, text: ArbitraryText):
        self._xlog.debug(f"Handling ArbitraryText: Text='{text.text}'")
        self._process_pool.send(QUEUE_SPEAKER, XprocAction.SAY, text.text)
        # We have to wait until the speaker starts being busy, otherwise the mouth effect will self close
        while not self._process_pool.get_memory_manager().read_shared_memory_flag(SHARED_SPEAKER_BUSY):
            time.sleep(0.01)
        self._process_pool.send(QUEUE_MATRIX, XprocAction.SAY, text.text)

    def handle_chatbot_answer(self, answer: ChatbotAnswer):
        self._xlog.debug(f"Handling ChatbotAnswer: Question='{answer.question}', Answer='{answer.answer}'")

        self._process_pool.send(QUEUE_SPEAKER, XprocAction.SAY, answer.answer)
        # We have to wait until the speaker starts being busy, otherwise the mouth effect will self close
        while not self._process_pool.get_memory_manager().read_shared_memory_flag(SHARED_SPEAKER_BUSY):
            time.sleep(0.01)
        
        if answer.is_error:
            # This is actually controlled by the MatrixLED itself in show_kitt_mouth_while_speaking()
            # It checks if there is an error ongoing by reading the SHARED_CHATBOT_BUSY flag
            # TODO: Bring it here, to centralize it.
            pass

        self._process_pool.send(QUEUE_MATRIX, XprocAction.SAY, answer.answer)

        if answer.was_function_used:
            # This is controlled by the callbacks of the functions themselves.
            # TODO: Bring it here, to centralize it.
            # self._xlog.debug(f"Last function used: Name='{answer.last_function_name}', Arguments='{answer.last_function_arguments}', Result='{answer.last_function_result}'")
            # self._process_pool.send(QUEUE_EINK, XprocAction.SHOW_TALKING_ARBITRARY_EINK, data=answer.last_function_result)
            pass

    def handle_status_update(self, status: StatusUpdate):
        self._xlog.debug(f"Handling StatusUpdate: Type='{status.type}', Value='{status.value}'")

        if status.type == StatusType.INIT_PHASE:
            self._xlog.debug(f"Displaying INIT_PHASE status on the eInk display: Value='{status.value}'")
            self._process_pool.send(QUEUE_EINK, XprocAction.INIT_STEP, data=status.value)
        elif status.type == StatusType.HOLDING_INTERACTION:
            try:
                percentage = int(status.value)
                self._xlog.debug(f"Displaying HOLDING_INTERACTION status on the Matrix LED display: Percentage='{percentage}%'")
                self._process_pool.send(QUEUE_MATRIX, XprocAction.INTERACTION_HOLDING_PERCENTAGE, data=percentage)
            except Exception as e:
                self._xlog.error(f"Failed to parse HOLDING_INTERACTION percentage: Value='{status.value}', Error='{str(e)}'")
        else:
            self._xlog.debug(f"Status type '{status.type}' not handled specifically.")
    
    def handle_arbitrary_content(self, content: ArbitraryContent):
        self._xlog.debug(f"Handling ArbitraryContent: Text='{content.text}', While Talking='{content.while_talking}'")
        if content.while_talking:
            self._xlog.debug("Displaying ArbitraryContent (while talking) on the eInk display")
            self._process_pool.send(QUEUE_EINK, XprocAction.SHOW_TALKING_ARBITRARY_EINK, data=content)
        else:
            self._xlog.debug("Displaying ArbitraryContent on the eInk display")
            self._process_pool.send(QUEUE_EINK, XprocAction.SHOW_ARBITRARY_TEXT_EINK, data=content)