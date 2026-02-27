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

    # Display Foreground
    SHOW: str = "SHOW"
    STARTUP: str = "STARTUP"
    READY: str = "READY"
    SOFT_CLEAR: str = "SOFT_CLEAR"
    SHOW_IMAGE_EINK: str = "SHOW_IMAGE_EINK"    # Do not use.
    SHOW_IDLE: str = "SHOW_IDLE"
    SHOW_ARBITRARY_TEXT_FOREGROUND_SPEAKING: str = "SHOW_ARBITRARY_TEXT_FOREGROUND_SPEAKING"
    SHOW_ARBITRARY_TEXT_FOREGROUND_THINKING: str = "SHOW_ARBITRARY_TEXT_FOREGROUND_THINKING"
    SHOW_ARBITRARY_TEXT_FOREGROUND: str = "SHOW_ARBITRARY_TEXT_FOREGROUND"
    SHOW_ARBITRARY_ICON_FOREGROUND: str = "SHOW_ARBITRARY_ICON_FOREGROUND"
    SHOW_CODE_BLOCK: str = "SHOW_CODE_BLOCK"
    SHOW_ERROR: str = "SHOW_ERROR"

    # Common between eInk and LED
    CLEAR: str = "CLEAR"

    # Background
    LED: str = "LED"    # This should be removed, should not actually be used.
    INIT_STEP: str = "INIT_STEP"
    THINKING: str = "THINKING"
    COMMUNICATING: str = "COMMUNICATING"
    SHOW_IMAGE_LED: str = "SHOW_IMAGE_LED"  # This is not used.
    INTERACTION_HOLDING_PERCENTAGE: str = "INTERACTION_HOLDING_PERCENTAGE"

    # New Foreground actions
    FOREGROUND_CLEAR: str = "FOREGROUND_CLEAR"
    BACKGROUND_CLEAR: str = "BACKGROUND_CLEAR"

