class QueueItemType:

    # These expect a message as a parameter
    SAY: str = "say"
    SHOW: str = "show"

    # These expect something to do as a parameter
    ACTION: str = "action"
    DISPLAY: str = "display"
    MATRIX: str = "matrix"
    SPEECH: str = "speech"

    # This is meant to be the real work defined in subclasses
    DO: str = "do"

class QueueItemAction:

    FINISH: str = "finish"
    INITIALIZE: str = "initialize"

class QueueItemDisplay:

    CLEAR: str = "clear"
    SOFT_CLEAR: str = "soft_clear"
    STARTUP: str = "startup"
    READY: str = "ready"