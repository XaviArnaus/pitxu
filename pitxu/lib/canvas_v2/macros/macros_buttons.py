from PIL import ImageDraw

from pyxavi import Config, Dictionary
from pitxu.lib.objects import Point

from pitxu.lib.canvas_v2.layout_info import LayoutInfo
from pitxu.lib.canvas_v2.macros.macros_base import MacrosBase
from pitxu.lib.canvas_v2.buttons import SLOTS_PER_COLUMN


class MacrosButtons(MacrosBase):
    """
    Drawings that take place in the buttons areas: "bottom_left" and "bottom_right" of the layout.
    """

    SLOT_PADDING: int = 6
    SLOT_GAP: int = 4
    BUTTON_RADIUS: int = 6

    def __init__(self, config: Config, params: Dictionary):
        super(MacrosButtons, self).__init__(config, params)

        self._xlog.debug("Initialized MacrosButtons.")

    def _color(self, name: str) -> tuple | int:
        return self.canvas.COLOR_CODES[name][str(self.canvas.COLOR_MODE)]

    def draw_buttons_panel(self, draw: ImageDraw.ImageDraw, params: dict):
        '''
        Draws a whole column of buttons.
         The params should include:
            - display_area (str): "bottom_left" or "bottom_right".
            - buttons (list[dict]): one per button, with slot (1-based), label, color (a name) and active (bool).
        Active buttons are filled, inactive ones only outlined, so the layout never jumps.
        '''

        display_area: str = params.get("display_area", "bottom_left")
        buttons: list[dict] = params.get("buttons", [])

        # Frame of the area, same as the other macros do.
        self.base_frame_for_display_area(draw=draw, params={"display_area": display_area})

        slots = LayoutInfo.split_into_slots(
            self.layout_info["relative"][display_area],
            slots=SLOTS_PER_COLUMN,
            padding=self.SLOT_PADDING,
            gap=self.SLOT_GAP)

        for button in buttons:
            slot_index = button["slot"] - 1
            if not 0 <= slot_index < len(slots):
                self._xlog.warning(f"Button slot [{button['slot']}] is out of range (1-{len(slots)}). Skipping it.")
                continue

            slot = slots[slot_index]
            color = self._color(button["color"])
            active: bool = button["active"]

            draw.rounded_rectangle(
                slot.to_image_rectangle(),
                radius=self.BUTTON_RADIUS,
                outline=color,
                fill=color if active else None)

            # One line with an emoji and a number: if it doesn't fit in the slot, use the smaller font.
            font = self.canvas.FONT_SMALL
            if draw.textlength(button["label"], font=font) > (slot.point_2.x - slot.point_1.x) - 4:
                font = self.canvas.FONT_TINY

            draw.text(
                Point((slot.point_1.x + slot.point_2.x) // 2, (slot.point_1.y + slot.point_2.y) // 2).to_image_point(),
                text=button["label"],
                font=font,
                fill=self.canvas.COLOR_BLACK if active else color,
                anchor="mm",
                align="center",
                embedded_color=True)