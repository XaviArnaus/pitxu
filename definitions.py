import os

# File Paths
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(ROOT_DIR, "config")

# Process Names in the Pool
QUEUE_SPEAKER = "speaker_queue"
QUEUE_EINK = "eink_queue"
QUEUE_MATRIX = "matrix_queue"
QUEUE_LCD = "lcd_queue"
QUEUE_DSI_LCD = "dsi_lcd_queue"

# Shared memory flag positions
SHARED_MEMORY_FLAGS = "pitxu_shared_memory_flags"
SHARED_SPEAKER_BUSY = 0
SHARED_EINK_BUSY = 1
SHARED_MATRIX_BUSY = 2
SHARED_LCD_BUSY = 3
SHARED_DSI_LCD_BUSY = 4
SHARED_MICROPHONE_MUTED = 5
SHARED_CHATBOT_BUSY = 6
SHARED_CHATBOT_ANSWER_IS_ERROR = 7
SHARED_EINK_IDLE_MODE = 8
SHARED_LCD_IDLE_MODE = 9
SHARED_DSI_LCD_IDLE_MODE = 10
SHARED_NETWORK_BUSY = 11
SHARED_USER_IS_SPEAKING = 12

# Painter
LOOP_START: str = "start"
LOOP_END: str = "end"
FOREGROUND_CHANNEL: str = "foreground"
BACKGROUND_CHANNEL: str = "background"