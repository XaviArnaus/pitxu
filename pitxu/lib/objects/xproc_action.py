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
    # but it's not yet standarized
    DO: str = "DO"

    # Text To Speech.
    # Perhaps the displays show something too meanwhile.
    SAY: str = "SAY"

    # Display eInk
    SHOW: str = "SHOW"
    STARTUP: str = "STARTUP"
    READY: str = "READY"
    SOFT_CLEAR: str = "SOFT_CLEAR"
    EINK_CLEAR: str = "EINK_CLEAR"
    SHOW_IMAGE_EINK: str = "SHOW_IMAGE_EINK"    # Do not use.
    SHOW_IDLE_EINK: str = "SHOW_IDLE_EINK"
    SHOW_TALKING_ARBITRARY_EINK: str = "SHOW_TALKING_ARBITRARY_EINK"
    SHOW_ARBITRARY_TEXT_EINK: str = "SHOW_ARBITRARY_TEXT_EINK"

    # Common between eInk and LED
    CLEAR: str = "CLEAR"

    # Matrix LED
    LED: str = "LED"
    LED_CLEAR: str = "LED_CLEAR"
    INIT_STEP: str = "INIT_STEP"
    THINKING: str = "THINKING"
    SHOW_IMAGE_LED: str = "SHOW_IMAGE_LED"

