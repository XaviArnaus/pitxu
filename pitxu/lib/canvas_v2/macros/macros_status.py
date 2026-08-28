from PIL import ImageDraw

from pyxavi import Config, Dictionary, dd
from pitxu.lib.objects import Point

from pitxu.lib.canvas_v2.macros.macros_base import MacrosBase

class MacrosStatus(MacrosBase):
    """
    Drawings that take place in the status area, which is the "bottom-center" area of the layout.
    """

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
        self.base_frame_for_display_area(draw=draw, params={"display_area": "bottom_center"})

        # This is wrong, should be in the StatusQueue, so in a new MacrosStatus.
        #   That's why it's not shown, its out of the merging image frame.
        status_offset_x = self.layout_info["relative"]["bottom_center"].point_1.x
        status_offset_y = self.layout_info["relative"]["bottom_center"].point_1.y
        status_max_x = self.layout_info["relative"]["bottom_center"].point_2.x
        status_max_y = self.layout_info["relative"]["bottom_center"].point_2.y
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
        Draws a status line in the status area, which is the "bottom-center" area of the layout.
         The params should include:
            - text (str): The text to show in the status line.
            - color (str): The color of the text in the status lines.
         This is meant to be used for showing simple status lines, like "Listening...", "Thinking...", etc.
         For more complex interactions, like showing a progress bar or similar, a new method should be created, and called from the extended_status_run() method in the XprocessDisplayStatus subclass.
         This is not meant to be used for showing arbitrary text or images, those should be shown in the foreground or background areas, not in the status line.
         '''
        
        self.base_frame_for_display_area(draw=draw, params={"display_area": "bottom_center"})
        
        text: str = params.get("text", "")
        color: tuple | int = params.get("color", self.canvas.COLOR_FOREGROUND)

        draw.multiline_text(
            Point(
                # self.layout_info["relative"]["bottom_center"].point_1.x + (self.layout_info["relative"]["bottom_center"].point_2.x - self.layout_info["relative"]["bottom_center"].point_1.x) / 2,
                # self.layout_info["relative"]["bottom_center"].point_1.y + (self.layout_info["relative"]["bottom_center"].point_2.y - self.layout_info["relative"]["bottom_center"].point_1.y) / 2).to_image_point(),
                self.layout_info["relative"]["bottom_center"].point_1.x + 8,    # Add some padding from the left edge
                self.layout_info["relative"]["bottom_center"].point_1.y + 6).to_image_point(),  # Add some padding from the top edge
            # text=self.wrap_text_if_needed(
            #     canvas=draw,
            #     text="\n".join(self.status_lines),
            #     max_width=self.layout_info["relative"]["bottom_center"].point_2.x - self.layout_info["relative"]["bottom_center"].point_1.x - 20,
            #     font=self.canvas.FONT_SMALL
            #     ),
            text=text,
            font=self.canvas.FONT_TINY,
            fill=color,
            anchor="la",
            align="left")