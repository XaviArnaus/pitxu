import time

import numpy as np
from PIL import Image, ImageDraw

from pyxavi import Config, Dictionary

from pitxu.lib.canvas_v2.macros.macros_base import MacrosBase

from pitxu.lib.objects.size import Size
from pitxu.lib.canvas_v2.layout_info import DisplayArea

class MacrosAnimation(MacrosBase):
    """
    Drawings of the animations (the emojis), in the "top-left" area.

    It draws the frame of an animation, and the crossfade between two animations: when the animation on screen
    changes, the previous one keeps playing underneath while it fades out. See `_apply_crossfade()`.
    """

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config, params: Dictionary):
        super(MacrosAnimation, self).__init__(config, params)

        # The crossfade between two animations (see _apply_crossfade()). Tuned in the config under `animations.crossfade`.
        #   duration: seconds that both animations are blended. 0 turns it off.
        #   max_gap: it only applies when the previous animation was drawn at most this many seconds ago: if more time passed,
        #            the area was cleared in between and there is nothing to blend from.
        self.crossfade_duration: float = max(0.0, float(self._xconfig.get("animations.crossfade.duration", 0.25)))
        self.crossfade_max_gap: float = max(0.0, float(self._xconfig.get("animations.crossfade.max_gap", 0.25)))
        # The last animation drawn: name, frame index and when. And how long a frame of each animation lasts (as seen drawing it).
        self._last_animation_drawn: dict | None = None
        self._frame_interval_by_animation: dict[str, float] = {}
        # The crossfade going on, if any.
        self._crossfade: dict | None = None

        self.log_summary("Macros Animation Initialization", [
            ("animation crossfade", f"{self.crossfade_duration} s (only if the previous animation was drawn at most {self.crossfade_max_gap} s ago)"),
        ])

        self._xlog.debug("Initialized MacrosAnimation.")

    @staticmethod
    def _blend_frames(outgoing: Image.Image, incoming: Image.Image, weight: float) -> Image.Image:
        """
        Blends two RGBA frames of the same size: `weight` 0 is the outgoing frame, 1 is the incoming one.
        It is done with the colors premultiplied by their alpha, otherwise the (black) color under the transparent
        pixels would darken the edges while one emoji is fading in over the other.
        """
        if outgoing.size != incoming.size:
            return incoming
        out_array = np.asarray(outgoing.convert("RGBA"), dtype=np.float32)
        in_array = np.asarray(incoming.convert("RGBA"), dtype=np.float32)

        def premultiply(array: np.ndarray) -> np.ndarray:
            premultiplied = array.copy()
            premultiplied[..., :3] *= array[..., 3:4] / 255.0
            return premultiplied

        mixed = premultiply(out_array) * (1.0 - weight) + premultiply(in_array) * weight
        alpha = mixed[..., 3:4]
        result = np.zeros_like(mixed)
        np.divide(mixed[..., :3] * 255.0, alpha, out=result[..., :3], where=alpha > 0)
        result[..., 3:4] = alpha
        return Image.fromarray(np.clip(result + 0.5, 0, 255).astype(np.uint8), "RGBA")

    def _apply_crossfade(self, animation_name: str, frame_index: int, frame: Image.Image, size: Size) -> Image.Image:
        """
        Crossfade between animations: when the one being drawn is not the same as the previous one, the previous keeps
        playing (it advances with the time, at the pace it had) and fades out while the new one starts playing right away
        and fades in, for `animations.crossfade.duration` seconds. The new animation is never delayed: only its first
        frames show a bit of the old one. With the previous animation gone (not drawn for more than `max_gap`
        seconds) or the duration at 0, the frame is drawn as it is.

        Runs in the painter thread, the only one that draws animations, so it keeps its state without locks.

        Returns the frame to draw: the given one, or the blend.
        """
        if self.crossfade_duration <= 0:
            return frame

        now = time.monotonic()
        last = self._last_animation_drawn

        # How long a frame of this animation lasts, from the time between draws of consecutive frames.
        if last is not None and last["name"] == animation_name:
            elapsed = now - last["time"]
            if 0 < elapsed < 1.0:
                previous_interval = self._frame_interval_by_animation.get(animation_name, elapsed)
                self._frame_interval_by_animation[animation_name] = 0.7 * previous_interval + 0.3 * elapsed

        # A different animation right after another one: start fading from it.
        if last is not None and last["name"] != animation_name and (now - last["time"]) <= self.crossfade_max_gap:
            self._crossfade = {
                "from_name": last["name"],
                "from_index": last["index"],
                "from_time": last["time"],
                "from_interval": self._frame_interval_by_animation.get(last["name"], 0.05),
                "started": now,
            }
        self._last_animation_drawn = {"name": animation_name, "index": frame_index, "time": now}

        crossfade = self._crossfade
        if crossfade is None:
            return frame

        progress = (now - crossfade["started"]) / self.crossfade_duration
        if progress >= 1.0:
            self._crossfade = None
            return frame

        try:
            from_animation = self.animations.get_animation(crossfade["from_name"])
            steps = int((now - crossfade["from_time"]) / max(crossfade["from_interval"], 0.001))
            outgoing_index = (crossfade["from_index"] + steps) % max(from_animation.get_frame_count(), 1)
            outgoing = self.animations.get_animation_frame(crossfade["from_name"], outgoing_index, size)
        except Exception as e:
            self._log_debug(f"Crossfade skipped, the previous animation is not available: {e}")
            self._crossfade = None
            return frame

        # Eased, so it starts and ends smoothly instead of at constant speed.
        weight = progress * progress * (3.0 - 2.0 * progress)
        return self._blend_frames(outgoing, frame, weight)

    def merge_animation(self, base_image: Image.Image, params: dict):
        '''
        Draws a GIF on the LCD canvas.

        Args:
            draw: The canvas to draw on.
            params: A dictionary containing the parameters for the drawing.
                - gif_path: The path to the GIF file to draw.
        '''
        current_loop_iteration = params.get("current_loop_iteration", 0)
        max_loop_iterations = params.get("max_loop_iterations", 0)
        animation_name = params.get("animation", None)

        # Before anything, draw the display_area frame.
        draw = ImageDraw.Draw(base_image)
        self.base_frame_for_display_area(draw=draw, params={"display_area": DisplayArea.ANIMATIONS})

        # Peek into the loaded animation.
        animation = self.animations.get_animation(animation_name) if self.animations is not None else None
        if animation is None:
            self._xlog.error(f"Animation '{animation_name}' not found.")
            return

        self._log_debug(f"Loaded GIF '{animation_name}' with {animation.get_frame_count()} frames. Picking index {current_loop_iteration}")

        # Calculate the size to draw the frame, based on the layout info and the size of the frame.
        width = self.layout_info["relative"][DisplayArea.ANIMATIONS].point_2.x - self.layout_info["relative"][DisplayArea.ANIMATIONS].point_1.x
        height = self.layout_info["relative"][DisplayArea.ANIMATIONS].point_2.y - self.layout_info["relative"][DisplayArea.ANIMATIONS].point_1.y

        # Also, we want to keep the aspect ratio of the original GIF, but resized to fit inside the given width and height.
        original_width, original_height = animation.get_original_size()
        aspect_ratio = (original_width / original_height)
        if width / height > aspect_ratio:
            # We are limited by the height, we need to calculate the width based on the aspect ratio.
            desired_height_gif = height
            desired_width_gif = int(height * aspect_ratio)
        else:
            # We are limited by the width, we need to calculate the height based on the aspect ratio.
            desired_width_gif = width
            desired_height_gif = int(width / aspect_ratio)
        # Apply a final correction factor to make sure it fits into the display area, 
        # taking in account some padding and the rounded corners of the LCD.
        correction_factor = 0.8
        desired_width_gif = int(desired_width_gif * correction_factor)
        desired_height_gif = int(desired_height_gif * correction_factor)

        # Calculate which frame to show based on the current loop iteration and max loop iterations
        frame_size = Size(width=desired_width_gif, height=desired_height_gif)
        frame_to_show = self.animations.get_animation_frame(
            animation_name, 
            current_loop_iteration, 
            desired_size=frame_size)

        # When the animation changes, the previous one does not vanish: it keeps playing underneath while it fades out.
        frame_to_show = self._apply_crossfade(animation_name, current_loop_iteration, frame_to_show, frame_size)

        # Calculate the position to draw the frame, centered in the display area.
        offset_x = self.layout_info["relative"][DisplayArea.ANIMATIONS].point_1.x + ((width - desired_width_gif) // 2)
        offset_y = self.layout_info["relative"][DisplayArea.ANIMATIONS].point_1.y + ((height - desired_height_gif) // 2)

        # Paint the frame on the canvas, resizing it to fit into the display area if needed.
        # Composite it, do not paste it: a paste replaces the pixels including their alpha, so the transparent parts of the emoji
        #   would erase the fill of the area (a box around the emoji) instead of letting it show through.
        if base_image.mode == "RGBA" and frame_to_show.mode == "RGBA":
            base_image.alpha_composite(frame_to_show, dest=(offset_x, offset_y))
        else:
            frame_rgba = frame_to_show.convert("RGBA")
            base_image.paste(frame_rgba, (offset_x, offset_y), mask=frame_rgba)