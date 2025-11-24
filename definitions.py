import os

# File Paths
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(ROOT_DIR, "config")

# Process Names in the Pool
PROCESS_SPEAKER = "speaker_process"
PROCESS_EINK = "eink_process"
PROCESS_MATRIX = "matrix_process"

# Shared memory flag positions
SHARED_MEMORY_FLAGS = "pitxu_shared_memory_flags"
SHARED_SPEAKER_BUSY = 0
SHARED_EINK_BUSY = 1
SHARED_MATRIX_BUSY = 2
SHARED_MICROPHONE_MUTED = 3
SHARED_CHATBOT_BUSY = 4

# Shared memory vu meter positions
SHARED_MEMORY_VU_METER = "pitxu_shared_memory_vu_meter"
SHARED_VU_COL_1 = 0
SHARED_VU_COL_2 = 1
SHARED_VU_COL_3 = 2
SHARED_VU_COL_4 = 3

# Buttons
SHARED_GPIO_BUTTONS = "pitxu_shared_buttons_state"
SHARED_GPIO_BUTTON_GREEN_STATE: int = 0  # GPIO pin for the green switch

# LEDs
SHARED_GPIO_LEDS = "pitxu_shared_leds_state"
SHARED_GPIO_LED_BLUE_STATE: int = 0     # GPIO pin for the blue LED