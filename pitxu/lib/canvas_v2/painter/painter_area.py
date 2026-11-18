from __future__ import annotations

from PIL import Image

from pitxu.lib.canvas_v2.painter.paint_object import BasePaint


class PainterArea:
    """
    The state of one area of the screen, as the Painter sees it.

    The Painter keeps one of these per queue (see PainterQueue), and loops over them.
    Everything that belongs to a single area goes here, instead of in dicts keyed by the queue name.
    """

    def __init__(self, name: str):
        # The name of the queue (a PainterQueue value).
        self.name: str = name
        # What waits to be painted in this area. The first one is the current one.
        self.paints: list[BasePaint] = []
        # The image that this area is drawn on, the size of its rectangle in the layout.
        # Created when the painting loop starts (see Painter.resume_paint()).
        self.image: Image.Image | None = None
        # The drawing cache: the cache key of the last paint that was drawn here, and its drawing.
        # If the current paint has the same key, the drawing is reused instead of drawn again.
        self.cached_key: str | None = None
        self.cached_image: Image.Image | None = None

    def store_in_cache(self, key: str, image: Image.Image):
        self.cached_key = key
        self.cached_image = image

    def reset_cache(self):
        self.cached_key = None
        self.cached_image = None

    def current(self) -> BasePaint | None:
        """ The paint that is being painted in this area, if any. """
        return self.paints[0] if len(self.paints) > 0 else None

    def has_paints(self) -> bool:
        return len(self.paints) > 0
