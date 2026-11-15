from dataclasses import dataclass

from definitions import SHARED_MICROPHONE_MUTED, SHARED_TRANSCRIBER_BUSY, SHARED_CHATBOT_BUSY

# How many buttons fit in a column. Free slots simply stay empty.
SLOTS_PER_COLUMN: int = 4

# The display area where each column of buttons is drawn.
COLUMN_TO_DISPLAY_AREA: dict[str, str] = {
    "left": "bottom_left",
    "right": "bottom_right",
}


@dataclass(frozen=True)
class ButtonDefinition:
    name: str           # Unique. Also used in the cache key and the callback names.
    column: str         # "left" | "right"
    slot: int           # 1..SLOTS_PER_COLUMN, from top to bottom.
    flag: int           # Shared memory flag that drives the button.
    active_value: bool  # Value of the flag that means "button ON" (False for the muted flag).
    label: str          # Short text or an emoji. The column is only about 53 px wide.
    color: str          # Color NAME from Canvas.COLOR_CODES. It is resolved in the macro.


BUTTONS: list[ButtonDefinition] = [
    ButtonDefinition("microphone",    "left", 1, SHARED_MICROPHONE_MUTED, False, "MIC", "green"),
    ButtonDefinition("transcription", "left", 2, SHARED_TRANSCRIBER_BUSY, True,  "STT", "yellow"),
    ButtonDefinition("chatbot",       "left", 3, SHARED_CHATBOT_BUSY,      True,  "🧠",  "orange"),
    # Slot 4 stays free for the next button.
]