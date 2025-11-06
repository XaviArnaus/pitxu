class QueueItemType:

    SAY: str = "say"
    SHOW: str = "show"
    ACTION: str = "action"
    DISPLAY: str = "display"
    SPEECH: str = "speech"

class QueueItemAction:

    FINISH: str = "finish"
    INITIALIZE: str = "initialize"

class QueueItemDisplay:

    CLEAR: str = "clear"
    STARTUP: str = "startup"
    READY: str = "ready"