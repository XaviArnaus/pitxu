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
QUEUE_SUPPORT = "support_queue"
QUEUE_TRANSCRIBER = "transcriber_queue"

# Shared memory flag positions
SHARED_MEMORY_FLAGS = "pitxu_shared_memory_flags"
# const = index(int)
SHARED_SPEAKER_BUSY = 0
SHARED_EINK_BUSY = 1
SHARED_MATRIX_BUSY = 2
SHARED_LCD_BUSY = 3
SHARED_DSI_LCD_BUSY = 4
SHARED_MICROPHONE_MUTED = 5
SHARED_CHATBOT_BUSY = 6
SHARED_CHATBOT_ANSWER_IS_ERROR = 7
SHARED_IDLE_MODE = 8
SHARED_LCD_IDLE_MODE = 9
SHARED_DSI_LCD_IDLE_MODE = 10
SHARED_NETWORK_BUSY = 11
SHARED_VAD_DETECTED = 12
SHARED_SUPPORT_BUSY = 13
SHARED_STT_BUSY = 14
SHARED_TRANSCRIBER_BUSY = 15
SHARED_WAKE_UP_BUTTON_PRESSED = 16

# Shared Memory Values
SHARED_MEMORY_VALUES = "pitxu_shared_memory_values"
# const = index(int)
SHARED_DYNAMIC_RMS_SILENCE_THRESHOLD = 0
# Current level (0.0 - 1.0) of the audio being played by the speaker, published by the TTS to drive the speaking animation.
SHARED_SPEAKER_LEVEL = 1
# Epoch timestamp (time.time()) of the first audio written by the TTS in the current speech, for the latency log. 0.0 when not set.
SHARED_FIRST_AUDIO_TIMESTAMP = 2
# Levels (integer percentages, -1 = unknown) published by the LevelsSampler so the display can show them.
SHARED_MIC_VOLUME = 3
# The speaker's mixer setting (%, ALSA). Not the audio signal: see SHARED_SPEAKER_LEVEL.
SHARED_SPEAKER_VOLUME = 4
SHARED_BATTERY_LEVEL = 5
# Booleans published as values: 1 = yes, 0 = no, -1 = unknown.
SHARED_SPEAKER_MUTED = 6
SHARED_POWER_CABLE_CONNECTED = 7

# Painter
LOOP_START: str = "start"
LOOP_END: str = "end"
FOREGROUND_CHANNEL: str = "foreground"
BACKGROUND_CHANNEL: str = "background"