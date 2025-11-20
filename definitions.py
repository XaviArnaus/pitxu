import os

# File Paths
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(ROOT_DIR, "config")

# Process Names in the Pool
PROCESS_SPEAKER = "speaker_process"
PROCESS_EINK = "eink_process"
PROCESS_MATRIX = "matrix_process"

# Shared memory flag positions
SHARED_MEMORY_FLAGS = "pitxu_shared_memory"
SHARED_SPEAKER_BUSY = 0
SHARED_EINK_BUSY = 1
SHARED_MATRIX_BUSY = 2
SHARED_MICROPHONE_MUTED = 3