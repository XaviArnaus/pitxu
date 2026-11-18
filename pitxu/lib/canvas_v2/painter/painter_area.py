from __future__ import annotations

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

    def current(self) -> BasePaint | None:
        """ The paint that is being painted in this area, if any. """
        return self.paints[0] if len(self.paints) > 0 else None

    def has_paints(self) -> bool:
        return len(self.paints) > 0
