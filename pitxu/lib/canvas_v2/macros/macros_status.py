from PIL import ImageDraw

from pyxavi import Config, Dictionary
from pitxu.lib.objects import Point

from pitxu.lib.canvas_v2.macros.macros_base import MacrosBase
from pitxu.lib.canvas_v2.layout_info import DisplayArea

class MacrosStatus(MacrosBase):
    """
    Drawings that take place in the status area, which is the "bottom-center" area of the layout.
    """

    # Each status entry takes at most this many visual lines.
    STATUS_ENTRY_MAX_LINES: int = 2
    STATUS_PADDING_X: int = 8
    STATUS_PADDING_Y: int = 6
    STATUS_LINE_SPACING: int = 2

    def __init__(self, config: Config, params: Dictionary):
        super(MacrosStatus, self).__init__(config, params)

        self._xlog.debug("Initialized MacrosStatus.")
    
    def draw_combined_init_phase(self, draw: ImageDraw.ImageDraw, params: dict):
        '''
        Draws the combined status (bottom-center) and foreground (top-right) for the init phase. 
        It is meant to be used on the new Pitxu main, as it has more space to show both the progress and the details.
        The old Pitxu client should still use the draw_foreground_init_phase() due to the small screen.
        '''

        # Initial Background Paint clear
        self.base_frame_for_display_area(draw=draw, params={"display_area": DisplayArea.STATUS})

        # This is wrong, should be in the StatusQueue, so in a new MacrosStatus.
        #   That's why it's not shown, its out of the merging image frame.
        status_offset_x = self.layout_info["relative"][DisplayArea.STATUS].point_1.x
        status_offset_y = self.layout_info["relative"][DisplayArea.STATUS].point_1.y
        status_max_x = self.layout_info["relative"][DisplayArea.STATUS].point_2.x
        status_max_y = self.layout_info["relative"][DisplayArea.STATUS].point_2.y
        status_width = status_max_x - status_offset_x
        status_height = status_max_y - status_offset_y
        
        # Mocked features line
        mocked_line = "Chatbot, STT, TTS,\nFore, Back, UPS, GPIO"
        draw.text(Point(status_offset_x + status_width / 2, status_offset_y + status_height / 8 * 3).to_image_point(),
                    text = mocked_line, 
                    font = self.canvas.FONT_SMALL, 
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")
        
        # Phases
        phase = params.get("phase", 0)
        text = params.get("text", None)
        # This is test, should be shown in the StatusPaint
        draw.text(Point(status_offset_x + status_width / 2, status_offset_y + status_height / 8 * 6).to_image_point(),
            text = text,
            font = self.canvas.FONT_SMALL, 
            fill = self.canvas.COLOR_FOREGROUND,
            anchor = "mm",
            align = "center",
            embedded_color=True)
    
    def draw_status_line(self, draw: ImageDraw.ImageDraw, params: dict):
        '''
        Draws the status entries in the status area, which is the "bottom-center" area of the layout.
         The params should include:
            - entries (list[tuple[str, color]]): The history of entries, oldest first. Each one is
                the text, starting with an icon, and its color (None for the default one).
                The color can be a Canvas color name ("red"), or a Canvas color value.
         Each entry is wrapped with a hanging indent of the icon's width, so a continuation line
          clearly belongs to the entry above, and it is capped to STATUS_ENTRY_MAX_LINES lines.
          Only the newest entries that fit in the area are drawn.
         This is meant to be used for showing simple status lines, like "Listening...", "Thinking...", etc.
         For more complex interactions, like showing a progress bar or similar, a new method should be created, and called from the extended_status_run() method in the XprocessDisplayStatus subclass.
         This is not meant to be used for showing arbitrary text or images, those should be shown in the foreground or background areas, not in the status line.
         '''

        self.base_frame_for_display_area(draw=draw, params={"display_area": DisplayArea.STATUS})

        entries = self._get_status_entries(params)
        if len(entries) == 0:
            return

        area = self.layout_info["relative"][DisplayArea.STATUS]
        x = area.point_1.x + self.STATUS_PADDING_X
        top = area.point_1.y + self.STATUS_PADDING_Y
        max_width = area.point_2.x - area.point_1.x - 2 * self.STATUS_PADDING_X
        max_height = area.point_2.y - area.point_1.y - 2 * self.STATUS_PADDING_Y

        font = self.canvas.FONT_TINY
        ascent, descent = font.getmetrics()
        line_height = ascent + descent + self.STATUS_LINE_SPACING

        # Lay out from the newest to the oldest, until the area is full.
        laid_out = []
        used_height = 0
        for text, color in reversed(entries):
            icon, lines, indent = self._layout_status_entry(draw, text, font, max_width)
            if used_height + len(lines) * line_height > max_height:
                break
            used_height += len(lines) * line_height
            laid_out.append((icon, lines, indent, color))
        laid_out.reverse()

        y = top
        for icon, lines, indent, color in laid_out:
            fill = self._resolve_status_color(color)
            if icon:
                draw.text((x, y), icon, font=font, fill=fill, anchor="la", embedded_color=True)
            for line in lines:
                draw.text((x + indent, y), line, font=font, fill=fill, anchor="la")
                y += line_height

    def _get_status_entries(self, params: dict) -> list[tuple[str, any]]:
        """
        Returns the entries to draw as a list of (text, color). It also accepts the old
        shape, a "text" with several lines and one "color" for all of them.
        """
        entries = params.get("entries", None)
        if entries is not None:
            return [(str(text), color) for text, color in entries]
        color = params.get("color", None)
        return [(line, color) for line in str(params.get("text", "")).split("\n") if line != ""]

    def _resolve_status_color(self, color: any) -> tuple | int:
        """
        None is the default color, a string is a Canvas color name, anything else is a color value.
        """
        if color is None:
            return self.canvas.COLOR_FOREGROUND
        if isinstance(color, str):
            codes = self.canvas.COLOR_CODES.get(color, None)
            if codes is None:
                self._xlog.warning(f"Unknown status color '{color}', using the default one.")
                return self.canvas.COLOR_FOREGROUND
            return codes[str(self.canvas.COLOR_MODE)]
        return color

    def _layout_status_entry(self, draw: ImageDraw.ImageDraw, text: str, font, max_width: float) -> tuple[str, list[str], float]:
        """
        Splits an entry in its icon and the lines of its text, wrapped to fit the width
        after the icon, with a maximum of STATUS_ENTRY_MAX_LINES, ending with "…" if cut.

        Returns:
            (icon, lines, indent): the icon ("" if none), the wrapped lines, and the indent in pixels.
        """
        text = text.replace("\n", " ").strip()
        icon = ""
        if text and not text[0].isalnum():
            icon, _, text = text.partition(" ")
        indent = draw.textlength(icon + " ", font=font) if icon else 0
        available = max_width - indent

        # A word that is wider than a whole line (a URL, say) is split in pieces.
        lines = self.wrap_text_to_lines(draw, text, available, font, hard_split=True)

        if len(lines) > self.STATUS_ENTRY_MAX_LINES:
            lines = lines[:self.STATUS_ENTRY_MAX_LINES]
            last = lines[-1]
            while last and draw.textlength(last + "…", font=font) > available:
                last = last[:-1]
            lines[-1] = last.rstrip() + "…"

        return icon, lines, indent