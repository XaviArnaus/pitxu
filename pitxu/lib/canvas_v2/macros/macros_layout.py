from PIL import ImageDraw, Image

from pyxavi import Config, Dictionary, dd
from pitxu.lib.objects import Rectangle, Point

from pitxu.lib.canvas_v2.macros.macros_base import MacrosBase

class MacrosLayout(MacrosBase):
    """
    Class to draw the layout frame, as a base canvas where all other display areas paint over.
    """

    def __init__(self, config: Config, params: Dictionary):
        super(MacrosLayout, self).__init__(config, params)

        self._xlog.debug("Initialized MacrosLayout.")
    
    def draw_overall_full_frame(self, draw: ImageDraw.ImageDraw, padding: int = 10, radius: int = 10, frame_color: str = None, opacity: float = 0.25):
        '''
        Draws a full screen frame on the given canvas, with the given padding and radius.

        It is meant to be used as an overlay for the whole screen, to show any specific interaction.

        2026-06-14: This method is currently not used.
        '''
        if frame_color is None:
            frame_color = self.canvas.COLOR_ORANGE

        if self.canvas.COLOR_MODE == "RGBA":
            TINT_COLOR = frame_color
            # Sorry, fellow reader, I understand "less transparency, more opaque", so 0.25 opacity is closer to no-transparent.
            TRANSPARENCY = opacity  # Degree of transparency, 0-100%
            OPACITY = int(255 * TRANSPARENCY)
            color = (TINT_COLOR[0], TINT_COLOR[1], TINT_COLOR[2], OPACITY)

            # Create an overlay image for the transparency effect
            overlay = Image.new(
                'RGBA', 
                self._display_size.to_image_point(), 
                (TINT_COLOR[0], TINT_COLOR[1], TINT_COLOR[2], 0))
            # Create a context for drawing things on it.
            draw_overlay = ImageDraw.Draw(overlay)

            # Draw a rounded rectangle on the overlay
            point_1 = Point(padding, padding)
            point_2 = Point(self._display_size.x - padding, self._display_size.y - padding)
            draw_overlay.rounded_rectangle(
                Rectangle(point_1, point_2).to_image_rectangle(),
                radius=radius,
                outline=frame_color,
                fill=color,
                corners=(True, True, True, True))

            # Now composite the overlay onto the original image
            self.canvas.combine_into_image(overlay)
        else:
            color = self.canvas.COLOR_BACKGROUND

            point_1 = Point(padding, padding)
            point_2 = Point(self._display_size.x - padding - 1, self._display_size.y - padding - 1)
            draw.rectangle(
                Rectangle(point_1, point_2).to_image_rectangle(),
                outline=frame_color,
                fill=color)
    
    def draw_foreground_frame(self, draw: ImageDraw.ImageDraw, padding: int = 10, radius: int = 10, frame_color: str = None, opacity: float = 0.25):
        '''
        Draws a foreground frame on the given canvas, except if the Color Mode is "1" (monochrome),
        in which case it draws a solid empty rectangle.

        https://stackoverflow.com/a/43620169/1973860
        '''

        # The screen is divided in 2 rows:
        #   - top: contains current interaction: mouth and text (question and answer)
        #   - bottom: contains additional information or status: buttons/icons and current action being executed.
        #
        # Top-left:
        #   - Interaction animation (mouth, emojis, etc.)
        # Top-right:
        #   - Current question and answer text (as has been fukll screen centered until now)
        # Bottom-left:
        #   - Status icons (Wifi, battery, etc.)
        # Bottom-center:
        #   - Current action being executed ("STT", "Chatbot", "External Tool (which)", etc.)
        # Bottom-right:
        #   - Action icons, color by action (STT grey: inactive, orange: transcribing but useless, green: transcribing to be used; Chatbot grey: inactive, blue: sent, orange: external tool, green: answering; Memory:...)
        #
        # Now defining the frame points
        # TODO: All of this should be re-thought. This should be a template, stored externally


        if self.canvas.COLOR_MODE == "RGBA":

            overlay: Image.Image = self.color_scheme_info["overlay_image"]
            overlay = overlay.copy()  # We copy it to avoid modifying the original one, which is stored in the color scheme info for re-use in other frames.
            draw_overlay = ImageDraw.Draw(overlay)

            # Draw all the rectangles given (they are already calculated to be inside the screen and with the padding)
            for name, rectangle in self.layout_info["padded"].items():
                # We actively avoid to draw the full screen rectangle, as it is meant to be used as a base for the other ones, and drawing it would cover the rest of the rectangles.
                if name == "full_screen":
                    continue
                draw_overlay.rounded_rectangle(
                    rectangle.to_image_rectangle(),
                    radius=radius,
                    outline=self.color_scheme_info[name]["outline"],
                    fill=self.color_scheme_info[name]["fill"],
                    # fill = self.canvas.COLOR_BACKGROUND
                    corners=(True, True, True, True))

            # Now composite the overlay onto the original image
            self.canvas.combine_into_image(overlay)
        else:
            if frame_color is None:
                frame_color = self.canvas.COLOR_ORANGE
            color = self.canvas.COLOR_BACKGROUND

            point_1 = Point(padding, padding)
            point_2 = Point(self._display_size.x - padding - 1, self._display_size.y - padding - 1)
            draw.rectangle(
                Rectangle(point_1, point_2).to_image_rectangle(),
                outline=frame_color,
                fill=color)