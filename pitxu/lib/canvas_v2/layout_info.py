
from PIL import Image

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.objects import Rectangle, Point
from pitxu.lib.canvas_v2.canvas import Canvas

import math

class DisplayArea:
    """
    The areas of the screen, named by what is shown in them. The value is the key of the area in the layout.
    To move an intention to another area, change it here.
    """
    # Animations and effects
    # ⚠️ Temporary: the Background queue still draws here, under the name EFFECTS, until the move to BACKGROUND.
    EFFECTS: str = "top_left"
    # What reacts to the state of the system in the background (the mouth, the countdown bar...), under the animations
    BACKGROUND: str = "center_left"
    # Texts, feedback and other messages
    MESSAGES: str = "top_right"
    # The status line
    STATUS: str = "bottom_center"
    # The columns of status buttons
    BUTTONS_LEFT: str = "bottom_left"
    BUTTONS_RIGHT: str = "bottom_right"
    # Overlays that cover everything
    OVERALL: str = "full_screen"


class LayoutInfo(PyXavi):
    """
    Information about the layout, to be used across the app.
    """
    canvas: Canvas = None
    _display_size: Point = None

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config, params: Dictionary):
        super(LayoutInfo, self).init_pyxavi(config=config, params=params)

        # We're supposed to receive a Canvas object in the params, initialized specifically for the intended device.
        if params.key_exists("canvas"):
            self.canvas = params.get("canvas")
            self._display_size = self.canvas.get_screen_size()
        else:
            self._xlog.error("No Canvas object received in params for Macros class")
    
    def get_layout_info(self, padding: int = 10, corners_radius: int = 10) -> dict[str, Rectangle]:
        '''
        Returns the layout information of the LCD display, based on the padding and the division in 2 rows.

        It is meant to be used as a helper for drawing the foreground frame, but can be used for other purposes.
        '''
        # The bottom row holds the buttons columns (SLOTS_PER_COLUMN slots each) and the status area.
        # The buttons take their height from this row: split_into_slots() divides what is left in the column.
        # ⚠️ If SLOTS_PER_COLUMN changes, review this too: 3 slots on 800x480 end up 35 px tall.
        rows_percentages = [0.7, 0.3]
        top_columns_percentages = [0.3, 0.7]
        bottom_columns_percentages = [0.10, 0.8, 0.10]

        # These are the areas of the screen where to merge the elements.
        # They do not include the margins. The offsets are calculated only so we can merge the display areas inside the main image.
        # The left column of the top row. It is not an area: top_left and center_left share it, see below.
        base_left_column = Rectangle(
            Point(0,0),
            Point(math.ceil(self._display_size.x * top_columns_percentages[0]), math.ceil(self._display_size.y * rows_percentages[0]))
        )
        base_top_right = Rectangle(
            Point(math.ceil(self._display_size.x * top_columns_percentages[0]), 0),
            Point(self._display_size.x, math.ceil(self._display_size.y * rows_percentages[0]))
        )
        base_bottom_left = Rectangle(
            Point(0, math.ceil(self._display_size.y * rows_percentages[0])),
            Point(math.ceil(self._display_size.x * bottom_columns_percentages[0]), self._display_size.y)
        )
        base_bottom_center = Rectangle(
            Point(math.ceil(self._display_size.x * bottom_columns_percentages[0]), math.ceil(self._display_size.y * rows_percentages[0])),
            Point(math.ceil((self._display_size.x) * (bottom_columns_percentages[0] + bottom_columns_percentages[1])), self._display_size.y)
        )
        base_bottom_right = Rectangle(
            Point(math.ceil((self._display_size.x * bottom_columns_percentages[0]) + (self._display_size.x * bottom_columns_percentages[1])), math.ceil(self._display_size.y * rows_percentages[0])),
            Point(self._display_size.x, self._display_size.y)
        )
        base_full_screen = Rectangle(
            Point(0,0), 
            Point(self._display_size.x, self._display_size.y)
        )

        # These are the the sizes relatives to each area.
        # This means that the offsets are calculated to be relative to the area, not to the full screen.
        # They include the margins, so they are the ones to draw above, not to be used to merge into the main image.
        relative_top_right = Rectangle(
            Point(padding // 2, padding),
            Point((base_top_right.point_2.x - base_top_right.point_1.x) - padding, (base_top_right.point_2.y - base_top_right.point_1.y) - (padding // 2))
        )
        relative_bottom_left = Rectangle(
            Point(padding, padding // 2),
            Point((base_bottom_left.point_2.x - base_bottom_left.point_1.x) - (padding // 2), (base_bottom_left.point_2.y - base_bottom_left.point_1.y) - padding)
        )
        relative_bottom_center = Rectangle(
            Point(padding // 2, padding // 2),
            Point((base_bottom_center.point_2.x - base_bottom_center.point_1.x) - (padding // 2), (base_bottom_center.point_2.y - base_bottom_center.point_1.y) - padding)
        )
        relative_bottom_right = Rectangle(
            Point(padding // 2, padding // 2),
            Point((base_bottom_right.point_2.x - base_bottom_right.point_1.x) - padding, (base_bottom_right.point_2.y - base_bottom_right.point_1.y) - padding)
        )
        relative_full_screen = Rectangle(
            Point(padding, padding),
            Point(self._display_size.x - padding, self._display_size.y - padding)
        )

        # These are the areas with the right offsets to paint the elements, that include the margins.
        # Should be the ones to draw above, not to be used to merge into the main image.
        # TODO: Refactor the code so we don't have to calculate the offsets in 2 different places, as this is error-prone.
        useful_width = self._display_size.x - (2 * padding) + 1
        useful_height = self._display_size.y - (2 * padding) + 2

        padded_left_column = Rectangle(
            Point(padding, padding),
            Point(math.ceil(useful_width * top_columns_percentages[0]), (padding // 2) + math.ceil(useful_height * rows_percentages[0]))
        )
        top_right = Rectangle(
            Point(padding + math.ceil(useful_width * top_columns_percentages[0]), padding),
            Point(padding + useful_width, (padding // 2) + math.ceil(useful_height * rows_percentages[0]))
        )
        bottom_left = Rectangle(
            Point(padding, padding + (padding // 2) + math.ceil(useful_height * rows_percentages[0])),
            Point(padding + math.ceil(useful_width * bottom_columns_percentages[0]), padding + useful_height)
        )
        bottom_center = Rectangle(
            Point((padding * 2) + math.ceil(useful_width * bottom_columns_percentages[0]), padding + (padding // 2) + math.ceil(useful_height * rows_percentages[0])),
            Point((padding * 2) + math.ceil((useful_width - padding) * (bottom_columns_percentages[0] + bottom_columns_percentages[1])), padding + useful_height)
        )
        bottom_right = Rectangle(
            Point((padding * 2) + math.ceil((useful_width * bottom_columns_percentages[0]) + (useful_width * bottom_columns_percentages[1])), padding + (padding // 2) + math.ceil(useful_height * rows_percentages[0])),
            Point(padding + useful_width, padding + useful_height)
        )
        full_screen = Rectangle(
            Point(padding, padding),
            Point(padding + useful_width, padding + useful_height)
        )

        # The left column of the top row holds two sibling areas, top_left (above) and center_left (below), like any other.
        # They are calculated from the column, and the relative ones from the padded ones, so they can't drift apart.
        center_left_height_share = float(self._xconfig.get("dsi_lcd.layout.center_left.height_share", 0.3))
        center_left_gap = int(self._xconfig.get("dsi_lcd.layout.center_left.gap", 6))
        if not 0.1 <= center_left_height_share <= 0.9:
            raise ValueError(f"'dsi_lcd.layout.center_left.height_share' must be between 0.1 and 0.9, got {center_left_height_share}.")
        if center_left_gap < 0:
            raise ValueError(f"'dsi_lcd.layout.center_left.gap' can't be negative, got {center_left_gap}.")

        left_column_usable_height = (padded_left_column.point_2.y - padded_left_column.point_1.y) - center_left_gap
        center_left_height = round(left_column_usable_height * center_left_height_share)
        top_left_height = left_column_usable_height - center_left_height

        top_left = Rectangle(
            padded_left_column.point_1,
            Point(padded_left_column.point_2.x, padded_left_column.point_1.y + top_left_height)
        )
        center_left = Rectangle(
            Point(padded_left_column.point_1.x, top_left.point_2.y + center_left_gap),
            padded_left_column.point_2
        )

        # The areas of the screen (the images to merge) share the column, split in the middle of the gap.
        split_y = top_left.point_2.y + (center_left_gap // 2)
        base_top_left = Rectangle(
            base_left_column.point_1,
            Point(base_left_column.point_2.x, split_y)
        )
        base_center_left = Rectangle(
            Point(base_left_column.point_1.x, split_y),
            base_left_column.point_2
        )

        # The relative ones are the padded ones, in the coordinates of their own area.
        def relative_to(base: Rectangle, padded: Rectangle) -> Rectangle:
            return Rectangle(
                Point(padded.point_1.x - base.point_1.x, padded.point_1.y - base.point_1.y),
                Point(padded.point_2.x - base.point_1.x, padded.point_2.y - base.point_1.y)
            )
        relative_top_left = relative_to(base_top_left, top_left)
        relative_center_left = relative_to(base_center_left, center_left)

        return {
            "base": {
                "top_left": base_top_left,
                "center_left": base_center_left,
                "top_right": base_top_right,
                "bottom_left": base_bottom_left,
                "bottom_center": base_bottom_center,
                "bottom_right": base_bottom_right,
                "full_screen": base_full_screen,
            },
            "relative": {
                "top_left": relative_top_left,
                "center_left": relative_center_left,
                "top_right": relative_top_right,
                "bottom_left": relative_bottom_left,
                "bottom_center": relative_bottom_center,
                "bottom_right": relative_bottom_right,
                "full_screen": relative_full_screen,
            },
            "padded": {
                "top_left": top_left,
                "center_left": center_left,
                "top_right": top_right,
                "bottom_left": bottom_left,
                "bottom_center": bottom_center,
                "bottom_right": bottom_right,
                "full_screen": full_screen,
            },
            "params": {
                "padding": padding,
                "corners_radius": corners_radius,
            }
        }
    
    def get_color_scheme_info(self, frame_color: str = None, opacity: float = 0.25) -> dict[str, dict[str, any]]:
        """
        Returns the color scheme information for the different areas of the LCD display, based on the color mode.
        """

        # -- Let's start by a simple default, no RGBA --
        # This will be the outline color.
        if frame_color is None:
            frame_color = self.canvas.COLOR_ORANGE
        # Now the fill color.
        fill_color = self.canvas.COLOR_BACKGROUND
        # This is not needed by the non-RGBA modes, but we define it here to avoid having it undefined in the RGBA mode.
        overlay: Image.Image = None

        # -- Now, if we have RGBA --
        if self.canvas.COLOR_MODE == "RGBA":

            # These are for the normal areas, with the intended color and transparency.
            fill_color, overlay = self.get_color_scheme_parts(
                frame_color=frame_color, 
                opacity=opacity)

            # These are only for the full screen overlays used by Code and Text blocks.
            fill_color_full_screen, overlay_full_screen = self.get_color_scheme_parts(
                frame_color=self.canvas.COLOR_WHITE, 
                opacity=0.85)

        return {
            "top_left": {
                "outline": frame_color,
                # We don't want any background in the top-left corner
                "fill": self.canvas.COLOR_BACKGROUND
            },
            "center_left": {
                "outline": frame_color,
                # Same as top-left: no background
                "fill": self.canvas.COLOR_BACKGROUND
            },
            "top_right": {
                "outline": frame_color,
                "fill": fill_color
            },
            "bottom_left": {
                "outline": frame_color,
                "fill": fill_color
            },
            "bottom_center": {
                "outline": frame_color,
                "fill": fill_color
            },
            "bottom_right": {
                "outline": frame_color,
                "fill": fill_color
            },
            "full_screen": {
                "outline": self.canvas.COLOR_WHITE,
                "fill": fill_color_full_screen
            },
            "overlay_image": overlay,
            "overlay_image_full_screen": overlay_full_screen,
        }
        
    def get_color_scheme_parts(self, frame_color: str, opacity: float) -> tuple[tuple[int, int, int, float], Image.Image]:
        TINT_COLOR = frame_color
        # Sorry, fellow reader, I understand "less transparent, more opaque", so 0.25 opacity is closer to no-transparent.
        TRANSPARENCY = opacity  # Degree of transparency, 0-100%
        OPACITY = int(255 * TRANSPARENCY)
        fill_color = (TINT_COLOR[0], TINT_COLOR[1], TINT_COLOR[2], OPACITY)

        # Create an overlay image for the transparency effect.
        # ATTENTION: This is meant to be a template, copy it when using it!
        #   overlay.copy() to use it, as we will need to draw on it and we don't want to modify the original one.
        overlay = Image.new(
            'RGBA', 
            self._display_size.to_image_point(), 
            (TINT_COLOR[0], TINT_COLOR[1], TINT_COLOR[2], 0))
        
        return fill_color, overlay

    @staticmethod
    def split_into_slots(area: Rectangle, slots: int, padding: int = 6, gap: int = 4) -> list[Rectangle]:
        '''
        Splits an area into `slots` equal rows, from top to bottom, leaving `padding` around and `gap` between them.
        The result is in the same coordinates as the given area.
        '''
        x1 = area.point_1.x + padding
        y1 = area.point_1.y + padding
        x2 = area.point_2.x - padding
        y2 = area.point_2.y - padding
        slot_height = (y2 - y1) // slots
        return [
            Rectangle(
                Point(x1, y1 + (index * slot_height) + (gap // 2)),
                Point(x2, y1 + ((index + 1) * slot_height) - (gap // 2)))
            for index in range(slots)
        ]