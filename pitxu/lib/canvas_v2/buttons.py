from dataclasses import dataclass
from typing import Callable

from definitions import SHARED_MICROPHONE_MUTED, SHARED_TRANSCRIBER_BUSY, SHARED_CHATBOT_BUSY, \
                        SHARED_MIC_VOLUME, SHARED_SPEAKER_VOLUME, SHARED_BATTERY_LEVEL, \
                        SHARED_SPEAKER_MUTED, SHARED_POWER_CABLE_CONNECTED
from pitxu.lib.canvas_v2.layout_info import DisplayArea

# How many buttons fit in a column. Free slots simply stay empty.
SLOTS_PER_COLUMN: int = 4

# The display area where each column of buttons is drawn.
COLUMN_TO_DISPLAY_AREA: dict[str, str] = {
    "left": DisplayArea.BUTTONS_LEFT,
    "right": DisplayArea.BUTTONS_RIGHT,
}

# What a value button shows when the value is unknown.
UNKNOWN_TEXT: str = "--"


@dataclass(frozen=True)
class ButtonDefinition:
    """
    A button is driven by shared memory, and comes in two kinds:
        - "flag": ON or OFF depending on a flag. Uses flag, active_value, label and color.
        - "value": shows a level. Uses value (a shared memory VALUE index), render and, optionally, an extra value
            that render() receives (the cable for the battery, the mute for the speaker): 1, 0 or -1 (unknown).
            render(value, extra, config) -> (label, color name, active). Value is an int, -1 means unknown.
            Active buttons are filled, inactive ones only outlined.
    """
    name: str           # Unique. Also used in the cache key and the callback names.
    column: str         # "left" | "right"
    slot: int           # 1..SLOTS_PER_COLUMN, from top to bottom.
    kind: str           # "flag" | "value"
    flag: int | None = None                     # flag kind: shared memory FLAG index
    active_value: bool = True                   # flag kind: the value of the flag that means "button ON"
    label: str = ""                             # flag kind: short text or an emoji
    color: str = ""                             # flag kind: color NAME from Canvas.COLOR_CODES
    value: int | None = None                    # value kind: shared memory VALUE index
    extra_value: int | None = None              # value kind: optional second VALUE that render() receives
    render: Callable | None = None              # value kind: render(value, extra, config) -> (label, color name, active)


def _number(value: int) -> str:
    return str(value) if value >= 0 else UNKNOWN_TEXT


def render_microphone_volume(value: int, extra: int | None, config) -> tuple[str, str, bool]:
    return f"🎤 {_number(value)}", "white", value >= 0


def render_speaker_volume(value: int, extra: int | None, config) -> tuple[str, str, bool]:
    # Some soundcards (like the WM8960) have no mute switch, only a volume: 0 is then the only way to silence them.
    if extra == 1 or value == 0:
        # Muted: just the glyph, in a color that catches the eye.
        return "🔇", "orange", True
    return f"🔊 {_number(value)}", "white", value >= 0


def render_battery(value: int, extra: int | None, config) -> tuple[str, str, bool]:
    # The socket replaces the battery while the power cable is connected.
    icon = "🔌" if extra == 1 else "🔋"
    if value < 0:
        return f"{icon} {UNKNOWN_TEXT}", "white", False
    warning_below = int(config.get("ups.battery_warning_below", 40))
    critical_below = int(config.get("ups.battery_critical_below", 15))
    if value < critical_below:
        color = "red"
    elif value < warning_below:
        color = "yellow"
    else:
        color = "green"
    return f"{icon} {value}", color, True


# Colors: the text of an active button is black, so use colors with contrast against it (not blue).
BUTTONS: list[ButtonDefinition] = [
    # Left column: status.
    ButtonDefinition("microphone",    "left", 1, kind="flag", flag=SHARED_MICROPHONE_MUTED, active_value=False, label="🎤",  color="green"),
    ButtonDefinition("transcription", "left", 2, kind="flag", flag=SHARED_TRANSCRIBER_BUSY, active_value=True,  label="STT", color="yellow"),
    ButtonDefinition("chatbot",       "left", 3, kind="flag", flag=SHARED_CHATBOT_BUSY,      active_value=True,  label="🧠",  color="orange"),
    # Slot 4 stays free for the next button.

    # Right column: levels.
    ButtonDefinition("microphone_volume", "right", 1, kind="value", value=SHARED_MIC_VOLUME,     render=render_microphone_volume),
    ButtonDefinition("speaker_volume",    "right", 2, kind="value", value=SHARED_SPEAKER_VOLUME, extra_value=SHARED_SPEAKER_MUTED,        render=render_speaker_volume),
    ButtonDefinition("battery",           "right", 3, kind="value", value=SHARED_BATTERY_LEVEL,  extra_value=SHARED_POWER_CABLE_CONNECTED, render=render_battery),
    # Slot 4 stays free for the next button.
]