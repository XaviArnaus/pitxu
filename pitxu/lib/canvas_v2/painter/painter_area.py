from __future__ import annotations

import threading

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

        # Who asked for a final clearing, until the painting loop takes the requests (see the take_*_requests methods).
        #   The names are only there to say it in the logs.
        self.area_clearing_requested_by: list[str] = []
        self.screen_clearing_requested_by: list[str] = []

        # The timers that remove a paint of this area after its maintain time, by the cache key of the paint.
        self.timers: dict[str, threading.Timer] = {}

    # ---- The paints that wait ----

    def current(self) -> BasePaint | None:
        """ The paint that is being painted in this area, if any. """
        return self.paints[0] if len(self.paints) > 0 else None

    def has_paints(self) -> bool:
        return len(self.paints) > 0

    def remove(self, paint: BasePaint, requester: str) -> bool:
        """
        Removes the given paint, but only if it is the current one: it may be that anything with more priority
        (or a duplicate) came in meanwhile, and the paint was already removed.
        Removing it also resets the drawing cache, and registers the final clearing requests that the paint asked for.

        Args:
            requester: The name to register in the clearing requests, to say who asked in the logs.

        Returns:
            bool: True if the paint was the current one and has been removed.
        """
        current = self.current()
        if current is None or current.name != paint.name:
            return False
        self.paints.pop(0)
        self.reset_cache()
        if paint.final_screen_clearing:
            self.request_screen_clearing(requester)
        if paint.final_area_clearing:
            self.request_area_clearing(requester)
        return True

    def remove_all(self):
        """ Empties the queue and resets the drawing cache. The timers are cancelled separately, see cancel_timers(). """
        self.paints = []
        self.reset_cache()

    def drop_duplicates_of_type(self, paint: BasePaint) -> list[BasePaint]:
        """
        Removes the paints that wait with the same command as the given one, because if they were not shown yet,
        there is no point in waiting: the flow already went somewhere else. Useful for scenarios like the init phases,
        when the next phase comes and the previous one was not shown.

        Kept: the other types; the current paint (so the loop iteration in progress is not affected) unless it says
        to be overwritten; and the given paint itself.

        Returns:
            list[BasePaint]: The paints that were dropped, so the caller can log them.
        """
        current = self.current()
        kept: list[BasePaint] = []
        dropped: list[BasePaint] = []
        for item in self.paints:
            if not item.command.matches(paint.command.get()):
                kept.append(item)
            elif current is not None and item.get_cache_key() == current.get_cache_key() and \
                    item.overwrite_current_interaction_with_same_type == False:
                kept.append(item)
            elif item.get_cache_key() == paint.get_cache_key():
                kept.append(item)
            else:
                dropped.append(item)
        self.paints = kept
        return dropped

    # ---- The drawing cache ----

    def store_in_cache(self, key: str, image: Image.Image):
        self.cached_key = key
        self.cached_image = image

    def reset_cache(self):
        self.cached_key = None
        self.cached_image = None

    def matches_cache(self, paint: BasePaint | None) -> bool:
        """
        Is the given paint (None for nothing) the same as the last one that was drawn here?
        Nothing matches nothing; and a paint matches if it has the same cache key.
        """
        if paint is None or self.cached_key is None:
            return paint is None and self.cached_key is None
        return paint.get_cache_key() == self.cached_key

    # ---- The timers ----

    def start_timer(self, key: str, seconds: float, callback: callable):
        """
        Starts a timer that calls the callback after the given seconds, in a thread of its own (so the callback must
        not touch the queues or the canvas, only ask the painting loop to do it).
        A timer with the same key is replaced: a paint with the same key (the idle one repeats every minute) must
        not inherit an older timer, otherwise the old one would remove the new paint too early.
        """
        previous_timer = self.timers.pop(key, None)
        if previous_timer is not None:
            previous_timer.cancel()

        def on_time():
            # Forget this timer, unless a newer one took its key.
            if self.timers.get(key) is timer:
                del self.timers[key]
            callback()

        timer = threading.Timer(seconds, on_time)
        timer.daemon = True
        self.timers[key] = timer
        timer.start()

    def cancel_timers(self) -> list[str]:
        """ Cancels all the timers of this area. Returns their keys, so the caller can log them. """
        keys = list(self.timers.keys())
        for timer in list(self.timers.values()):
            timer.cancel()
        self.timers = {}
        return keys

    # ---- The final clearing requests ----

    def request_area_clearing(self, requester: str):
        """ The area has to be cleared once the painting loop gets to it. """
        if requester not in self.area_clearing_requested_by:
            self.area_clearing_requested_by.append(requester)

    def request_screen_clearing(self, requester: str):
        """ The whole screen has to be cleared once the painting loop gets to it. """
        if requester not in self.screen_clearing_requested_by:
            self.screen_clearing_requested_by.append(requester)

    def take_area_clearing_requests(self) -> list[str]:
        """ Who asked for the area to be cleared. The requests are consumed: the next call returns nothing. """
        requesters, self.area_clearing_requested_by = self.area_clearing_requested_by, []
        return requesters

    def take_screen_clearing_requests(self) -> list[str]:
        """ Who asked for the screen to be cleared. The requests are consumed: the next call returns nothing. """
        requesters, self.screen_clearing_requested_by = self.screen_clearing_requested_by, []
        return requesters

    # ---- The rules of this area ----

    def is_priority(self, paint: BasePaint) -> bool:
        return paint.command.included_in(self.priority_commands)

    def is_exception_loop(self, paint: BasePaint) -> bool:
        return paint.command.included_in(self.exception_loop_commands)
