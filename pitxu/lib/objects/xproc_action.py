class XprocAction:
    '''
    All Xprocess queues work with a tuple: `(action, value)`.
    This class defines the actions.
    Some relate horizontally to all Xprocesses, some are specific.
    By now there won't be a disctinction, as we come from a too-much-defined
        and was a mess.
    '''

    # Common for all queues
    FINISH: str = "FINISH"
    INITIALIZE: str = "INITIALIZE"
    
    # This is meant to be the common real work action,
    # but it's not yet standarized.
    # It's not even used!
    DO: str = "DO"

    # Text To Speech.
    # Perhaps the displays show something too meanwhile.
    SAY: str = "SAY"
    GATHER_TTS: str = "GATHER_TTS"
    PLAY_TTS: str = "PLAY_TTS"
    SAY_OUTPUT_QUEUE: str = "SAY_OUTPUT_QUEUE"

    # Display Foreground specific
    INITIALIZE_ANIMATIONS: str = "INITIALIZE_ANIMATIONS"
    SHOW: str = "SHOW"
    STARTUP: str = "STARTUP"
    STARTUP_WITH_PHASE: str = "STARTUP_WITH_PHASE"
    READY: str = "READY"
    SOFT_CLEAR: str = "SOFT_CLEAR"
    SHOW_IMAGE_EINK: str = "SHOW_IMAGE_EINK"    # Do not use.
    SHOW_IDLE: str = "SHOW_IDLE"
    SHOW_ARBITRARY_TEXT_FOREGROUND_SPEAKING: str = "SHOW_ARBITRARY_TEXT_FOREGROUND_SPEAKING"
    SHOW_ARBITRARY_TEXT_FOREGROUND_THINKING: str = "SHOW_ARBITRARY_TEXT_FOREGROUND_THINKING"
    SHOW_ARBITRARY_TEXT_FOREGROUND_NETWORKING: str = "SHOW_ARBITRARY_TEXT_FOREGROUND_NETWORKING"
    SHOW_ARBITRARY_TEXT_FOREGROUND_IDLE: str = "SHOW_ARBITRARY_TEXT_FOREGROUND_IDLE"
    SHOW_ARBITRARY_TEXT_FOREGROUND: str = "SHOW_ARBITRARY_TEXT_FOREGROUND"
    SHOW_ARBITRARY_ICON_FOREGROUND_USER_SPEAKING: str = "SHOW_ARBITRARY_ICON_FOREGROUND_USER_SPEAKING"
    SHOW_ARBITRARY_ICON_FOREGROUND: str = "SHOW_ARBITRARY_ICON_FOREGROUND"
    SHOW_CODE_BLOCK: str = "SHOW_CODE_BLOCK"
    SHOW_CODE_BLOCK_WHILE_SPEAKING: str = "SHOW_CODE_BLOCK_WHILE_SPEAKING"
    SHOW_TEXT_BLOCK: str = "SHOW_TEXT_BLOCK"
    SHOW_TEXT_BLOCK_WHILE_SPEAKING: str = "SHOW_TEXT_BLOCK_WHILE_SPEAKING"
    SHOW_ERROR: str = "SHOW_ERROR"

    # Common between eInk and LED
    CLEAR: str = "CLEAR"

    # Background specific
    LED: str = "LED"    # This should be removed, should not actually be used.
    INIT_STEP: str = "INIT_STEP"
    THINKING: str = "THINKING"
    NETWORKING: str = "NETWORKING"
    SHOW_IMAGE_LED: str = "SHOW_IMAGE_LED"  # This is not used.
    INTERACTION_HOLDING_PERCENTAGE: str = "INTERACTION_HOLDING_PERCENTAGE"

    # Status specific
    STATUS_LINE: str = "STATUS_LINE"

    # New Foreground actions
    FOREGROUND_CLEAR: str = "FOREGROUND_CLEAR"
    BACKGROUND_CLEAR: str = "BACKGROUND_CLEAR"
    STATUS_CLEAR: str = "STATUS_CLEAR"

    # Support
    ACCUMULATE_AUDIO: str = "ACCUMULATE_AUDIO"
    ACCUMULATE_PREPROCESSED_AUDIO: str = "ACCUMULATE_PREPROCESSED_AUDIO"
    DUMP_AUDIO: str = "DUMP_AUDIO"
    DUMP_PREPROCESSED_AUDIO: str = "DUMP_PREPROCESSED_AUDIO"
    PLOT_AUDIO: str = "PLOT_AUDIO"
    CLEAR_AUDIOS: str = "CLEAR_AUDIOS"
    DUMP_ALL: str = "DUMP_ALL"
    SUMMARIZE_CHATBOT_HISTORY_AND_STORE_IN_MEMORY: str = "SUMMARIZE_CHATBOT_HISTORY_AND_STORE_IN_MEMORY"

    # Faster Whisper Stream specific
    TRANSCRIBE_CHUNK_WINDOW: str = "TRANSCRIBE_CHUNK_WINDOW"
    TRANSCRIBE_LEFTOVER_CHUNKS: str = "TRANSCRIBE_LEFTOVER_CHUNKS"
    RETRIEVE_TRANSCRIPTION_RESULT: str = "RETRIEVE_TRANSCRIPTION_RESULT"
    RESET_TRANSCRIPTION: str = "RESET_TRANSCRIPTION"

