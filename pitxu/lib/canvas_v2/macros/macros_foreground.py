from PIL import ImageDraw

from pyxavi import Config, Dictionary
from pitxu.lib.objects import Point, Rectangle

from pitxu.lib.canvas_v2.macros.macros_base import MacrosBase

class MacrosForeground(MacrosBase):
    """
    Drawings that take place in the foreground, which is the "top-right" area of the layout.
    """

    def __init__(self, config: Config, params: Dictionary):
        super(MacrosForeground, self).__init__(config, params)

        self._xlog.debug("Initialized MacrosForeground.")
    
    def draw_arbitrary_text_centered(self, draw: ImageDraw.ImageDraw, params: dict):
        text = params.get("text", "")

        # Initial Background Paint clear
        self.base_frame_for_display_area(draw=draw, params={"display_area": "top_right"})

        offset_x = self.layout_info["relative"]["top_right"].point_1.x
        offset_y = self.layout_info["relative"]["top_right"].point_1.y
        max_x = self.layout_info["relative"]["top_right"].point_2.x
        max_y = self.layout_info["relative"]["top_right"].point_2.y
        width = max_x - offset_x
        height = max_y - offset_y
    
        draw.text(Point(offset_x + width / 2, offset_y + height / 2).to_image_point(),
                    text = text,
                    font = self.canvas.FONT_HUGE,
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")
    
    def draw_arbitrary_text_with_icon(self, draw: ImageDraw.ImageDraw, params: dict):
        
        text = params.get("text", None)
        icon = params.get("icon", None)
        font_size = params.get("font_size", 24)
        header = params.get("header", None)
        font_header_size = params.get("font_header_size", 32)

        # Initial Background Paint clear
        self.base_frame_for_display_area(draw=draw, params={"display_area": "top_right"})
        
        offset_x = self.layout_info["relative"]["top_right"].point_1.x
        offset_y = self.layout_info["relative"]["top_right"].point_1.y
        max_x = self.layout_info["relative"]["top_right"].point_2.x
        max_y = self.layout_info["relative"]["top_right"].point_2.y
        width = max_x - offset_x
        height = max_y - offset_y

        # calculate anchor points and emojis for header and text
        if header and text:
            header_anchor = Point(offset_x + width / 2, offset_y + height / 3)
            text_anchor = Point(offset_x + width / 2, offset_y + (height / 4) * 3)
            header_emoji = icon + " " if icon else ""
            text_emoji = ""
        elif header and not text:
            header_anchor = Point(offset_x + width / 2, offset_y + height / 2)
            header_emoji = icon + " " if icon else ""
        elif not header and text:
            text_anchor = Point(offset_x + width / 2, offset_y + height / 2)
            text_emoji = icon + " " if icon else ""

        if header:
            draw.text(header_anchor.to_image_point(),
                text = f"{header_emoji}{header}",
                font = self.canvas.get_font_by_size(font_header_size),
                fill = self.canvas.COLOR_FOREGROUND,
                anchor = "mm",
                align = "center")

        if text:
            font = self.canvas.get_font_by_size(font_size)
            padding = 5
            value = self.wrap_text_if_needed(
                canvas=draw,
                text=f"{text_emoji}{text}",
                max_width=width - (2 * padding),
                font=font
            )
            draw.multiline_text(text_anchor.to_image_point(),
                text = value,
                font = font,
                fill = self.canvas.COLOR_FOREGROUND,
                anchor = "mm",
                align = "center")
    
    def draw_combined_init_phase(self, draw: ImageDraw.ImageDraw, params: dict):
        '''
        Draws the combined status (bottom-center) and foreground (top-right) for the init phase. 
        It is meant to be used on the new Pitxu main, as it has more space to show both the progress and the details.
        The old Pitxu client should still use the draw_foreground_init_phase() due to the small screen.
        '''

        # Initial Background Paint clear
        self.base_frame_for_display_area(draw=draw, params={"display_area": "top_right"})

        fore_offset_x = self.layout_info["relative"]["top_right"].point_1.x
        fore_offset_y = self.layout_info["relative"]["top_right"].point_1.y
        fore_max_x = self.layout_info["relative"]["top_right"].point_2.x
        fore_max_y = self.layout_info["relative"]["top_right"].point_2.y
        fore_width = fore_max_x - fore_offset_x
        fore_height = fore_max_y - fore_offset_y

        # This is wrong, should be in the StatusQueue, so in a new MacrosStatus.
        #   That's why it's not shown, its out of the merging image frame.
        # status_offset_x = self.layout_info["relative"]["bottom_center"].point_1.x
        # status_offset_y = self.layout_info["relative"]["bottom_center"].point_1.y
        # status_max_x = self.layout_info["relative"]["bottom_center"].point_2.x
        # status_max_y = self.layout_info["relative"]["bottom_center"].point_2.y
        # status_width = status_max_x - status_offset_x
        # status_height = status_max_y - status_offset_y

        # Main title
        title = self._xconfig.get("app.name")
        version = self._xparams.get("app_version")

        # ⚠️ Tried Pilmoji, but implies a complete refactor of the text drawing, and it's not worth it for now. 
        # Next, take a look at https://jdhao.github.io/2022/04/03/add_color_emoji_to_image_in_python/
        # self.text(
        #     draw=draw,
        #     xy=Point(fore_offset_x + fore_width / 2, fore_offset_y + fore_height / 3 * 1.5).to_image_point(),
        #     text = f"{title}  v{version}",
        #     font = self.canvas.FONT_HUGE, 
        #     fill = self.canvas.COLOR_FOREGROUND,
        #     anchor = "mm",
        #     align = "center")
        draw.text(Point(fore_offset_x + fore_width / 2, fore_offset_y + fore_height / 3 * 1.5).to_image_point(),
                    text = title + "  v" + version, 
                    font = self.canvas.FONT_HUGE, 
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")
        
        # # Mocked features line
        # mocked_line = "Chatbot, STT, TTS,\nFore, Back, UPS, GPIO"
        # draw.text(Point(status_offset_x + status_width / 2, status_offset_y + status_height / 8 * 3).to_image_point(),
        #             text = mocked_line, 
        #             font = self.canvas.FONT_SMALL, 
        #             fill = self.canvas.COLOR_FOREGROUND,
        #             anchor = "mm",
        #             align = "center")
        
        # Phases
        phase = params.get("phase", 0)
        text = params.get("text", None)
        # This is test, should be shown in the StatusPaint
        draw.text(Point(fore_offset_x + fore_width / 2, fore_offset_y + fore_height / 8 * 6).to_image_point(),
            text = text,
            font = self.canvas.FONT_SMALL, 
            fill = self.canvas.COLOR_FOREGROUND,
            anchor = "mm",
            align = "center",
            embedded_color=True)

    def draw_foreground_init_phase(self, draw: ImageDraw.ImageDraw, params: dict):
        '''
        Draws the foreground if the init phase. 
        This replaces the Background one used on Pitxu main. 
        Pitxu client should still use it due to the small screen.
        New Pitxu main should use a new status area (bottom-center) for the detailed, and the app name and version in the top-right

        2026-06-05: Offset and coords adapted to follow the self.layout_info. Assuming full screen.
        ⚠️ It won't work, I guess. Check when we iterate the Client.
        '''
        offset_x = self.layout_info["params"]["padding"]
        offset_y = self.layout_info["params"]["padding"]
        max_x = self._display_size.x - self.layout_info["params"]["padding"]
        max_y = self._display_size.y - self.layout_info["params"]["padding"]
        width = max_x - offset_x
        height = max_y - offset_y

        # Configurations
        padding_line = 15

        # Main title
        title = self._xconfig.get("app.name")
        version = self._xparams.get("app_version")
        draw.text(Point(offset_x + width / 2, offset_y + height / 8 * 1.5).to_image_point(),
                    text = title + "  v" + version, 
                    font = self.canvas.FONT_HUGE, 
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")
        
        # Mocked features line
        mocked_line = "Chatbot, STT, TTS,\nFore, Back, UPS, GPIO"
        draw.text(Point(offset_x + width / 2, offset_y + height / 8 * 4).to_image_point(),
                    text = mocked_line, 
                    font = self.canvas.FONT_SMALL, 
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")
        
        # Draw a line between the title and the subtitle
        draw.line(
            Rectangle(
                Point(offset_x + padding_line, offset_y + height / 3 * 2), 
                Point(offset_x + width - padding_line, offset_y + height / 3 * 2)
            ).to_image_rectangle(),
            fill = self.canvas.COLOR_FOREGROUND,
            width = 1)
        
        # Phases
        phase = params.get("phase", 0)
        text = params.get("text", None)
        draw.text(Point(offset_x + width / 2, offset_y + height / 8 * 6.5).to_image_point(),
                    # text = f"{phase} - {text}", 
                    text = text,
                    font = self.canvas.FONT_SMALL, 
                    fill = self.canvas.COLOR_FOREGROUND,
                    anchor = "mm",
                    align = "center")
    
    def draw_arbitrary_icon(self, draw: ImageDraw.ImageDraw, params: dict):
        '''
        Draws an arbitrary icon and text in the given color over the frame as is.

        2026-06-05: Offset and coords adapted to follow the self.layout_info. Assuming top-right area.
        '''
        offset_x = self.layout_info["relative"]["top_right"].point_1.x
        offset_y = self.layout_info["relative"]["top_right"].point_1.y
        max_x = self.layout_info["relative"]["top_right"].point_2.x
        max_y = self.layout_info["relative"]["top_right"].point_2.y
        width = max_x - offset_x
        height = max_y - offset_y

        color = params.get("color", self.canvas.COLOR_FOREGROUND)
        icon = params.get("icon", None)
        text = params.get("text", None)

        draw.text(Point(offset_x + width / 2, offset_y + height / 2 - (30 if text else 0)).to_image_point(),
                    text = icon,
                    font = self.canvas.FONT_ULTRA, 
                    fill = color,
                    anchor = "mm",
                    align = "center")
        if text:
            draw.text(Point(offset_x + width / 2, offset_y + height / 2 + 30).to_image_point(),
                    text = f"{icon}\n{text}" if text else icon, 
                    font = self.canvas.FONT_BIG, 
                    fill = color,
                    anchor = "mm",
                    align = "center")