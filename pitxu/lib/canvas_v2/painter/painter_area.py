from __future__ import annotations

from PIL import Image

from pitxu.lib.canvas_v2.painter.paint_object import BasePaint


class PainterArea:
    """
    The state of one area of the screen, as the Painter sees it.

    The Painter keeps one of these per queue (see PainterQueue), and loops over them.
    Everything that belongs to a single area goes here, instead of in dicts keyed by the queue name.
    """

    def __init__(
        self,
        name: str,
        layout_position: str,
        priority_commands: list[str] | None = None,
        exception_loop_commands: list[str] | None = None,
        slows_down_loop: bool = False
    ):
        # The name of the queue (a PainterQueue value).
        self.name: str = name
        # Where this area is in the layout (a DisplayArea value, the key of the area in the layout info).
        self.layout_position: str = layout_position

        # What waits to be painted in this area. The first one is the current one.
        self.paints: list[BasePaint] = []
        # The image that this area is drawn on, the size of its rectangle in the layout.
        # Created when the painting loop starts (see Painter.resume_paint()).
        self.image: Image.Image | None = None
        # The drawing cache: the cache key of the last paint that was drawn here, and its drawing.
        # If the current paint has the same key, the drawing is reused instead of drawn again.
        self.cached_key: str | None = None
        self.cached_image: Image.Image | None = None

        # These commands have priority over any other: when one arrives, everything waiting in this area is discarded.
        self.priority_commands: list[str] = list(priority_commands) if priority_commands else []
        # These commands are always drawn in every loop iteration, even if they did not change.
        self.exception_loop_commands: list[str] = list(exception_loop_commands) if exception_loop_commands else []
        # When this area has paints (and the areas that do not slow down have none), the loop slows down to avoid burning the CPU.
        self.slows_down_loop: bool = slows_down_loop

    # ---- The paints that wait ----

    def current(self) -> BasePaint | None:
        """ The paint that is being painted in this area, if any. """
        return self.paints[0] if len(self.paints) > 0 else None

    def has_paints(self) -> bool:
        return len(self.paints) > 0

    # ---- The drawing cache ----

    def store_in_cache(self, key: str, image: Image.Image):
        self.cached_key = key
        self.cached_image = image

    def reset_cache(self):
        self.cached_key = None
        self.cached_image = None

    # ---- The rules of this area ----

    def is_priority(self, paint: BasePaint) -> bool:
        return paint.command.included_in(self.priority_commands)

    def is_exception_loop(self, paint: BasePaint) -> bool:
        return paint.command.included_in(self.exception_loop_commands)
