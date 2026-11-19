import time
from contextlib import nullcontext


class _Stage:
    """ Times one stage of the painter loop and gives the result back to its PainterTimings. """

    __slots__ = ("_timings", "_name", "_start")

    def __init__(self, timings: "PainterTimings", name: str):
        self._timings = timings
        self._name = name

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._timings.record(self._name, time.perf_counter() - self._start)
        return False


class PainterTimings:
    """
    Measures where the time of the Painter loop goes, to know what is worth optimizing.

    It is meant to be used from the Painter thread only (the CPU time is the one of the thread that calls it).
    When it is not enabled, everything is a no-op, so it costs nothing to keep the calls in the loop.

    Every `interval` seconds of activity, and every time the loop pauses, it logs a summary:
    iterations per second, the CPU share of the Painter thread, and per stage the average and maximum milliseconds.
    A stage is anything that the loop measures with `measure(name)`. Counters (cache hits...) go with `count(name)`.
    """

    # If the loop is paused for longer than this between two iterations, the window restarts: the pause is not activity.
    PAUSE_GAP_SECONDS: float = 3.0

    def __init__(self, enabled: bool, log_callback: callable, interval: float = 10.0):
        """
        Args:
            enabled: If False, nothing is measured.
            log_callback: Receives the title and the lines (as tuples) of every summary.
            interval: Seconds of activity between summaries.
        """
        self.enabled: bool = enabled
        self._log_callback = log_callback
        self.interval: float = interval
        self._null_context = nullcontext()
        self._last_iteration_end: float | None = None
        self._iteration_start: float = 0.0
        self._reset()

    def _reset(self):
        self._window_start_wall: float | None = None
        self._window_start_cpu: float | None = None
        self._iterations: int = 0
        # name -> [count, total seconds, max seconds]
        self._stages: dict[str, list] = {}
        self._counters: dict[str, int] = {}

    # ---- What the loop calls ----

    def measure(self, name: str):
        """ A context manager to time a stage: `with timings.measure("flush"): ...` """
        if not self.enabled:
            return self._null_context
        return _Stage(self, name)

    def record(self, name: str, seconds: float):
        if not self.enabled:
            return
        stage = self._stages.get(name)
        if stage is None:
            self._stages[name] = [1, seconds, seconds]
        else:
            stage[0] += 1
            stage[1] += seconds
            if seconds > stage[2]:
                stage[2] = seconds

    def count(self, name: str, amount: int = 1):
        if not self.enabled:
            return
        self._counters[name] = self._counters.get(name, 0) + amount

    def iteration_start(self):
        """ Call at the beginning of every loop iteration (after the loop is resumed). """
        if not self.enabled:
            return
        now = time.perf_counter()
        self._iteration_start = now
        # A long gap means that the loop was paused: that time is not part of the measure.
        if self._last_iteration_end is not None and (now - self._last_iteration_end) > self.PAUSE_GAP_SECONDS:
            self._reset()
        if self._window_start_wall is None:
            self._window_start_wall = now
            self._window_start_cpu = time.thread_time()

    def iteration_end(self, drew: bool):
        """
        Call at the end of every loop iteration.
        Args:
            drew: False if the iteration decided that there was nothing to draw.
        """
        if not self.enabled:
            return
        now = time.perf_counter()
        self._iterations += 1
        # The whole iteration, waits and sleeps included: "iteration" minus "wait" and "slow_down_sleep" is the work.
        self.record("iteration", now - self._iteration_start)
        if not drew:
            self.count("iterations_without_drawing")
        self._last_iteration_end = now
        if self._window_start_wall is not None and (now - self._window_start_wall) >= self.interval:
            self.report("window")

    def loop_paused(self):
        """ Call right before the loop pauses: whatever was measured is reported, as it is the end of the activity. """
        if not self.enabled:
            return
        self.report("pause")
        self._last_iteration_end = None

    # ---- Reporting ----

    def report_stages(self, title: str):
        """
        For a piece of work that is not the loop (like drawing one block of text): logs the stages and counters measured
        since the last report, and forgets them. It does not need iterations, and it has nothing to do with the window
        of the loop, so it is meant for an instance of its own.
        """
        if not self.enabled or (not self._stages and not self._counters):
            return
        lines: list[tuple[str, str]] = []
        for name in sorted(self._stages.keys()):
            count, total, maximum = self._stages[name]
            lines.append((name, f"total {1000 * total:8.1f} ms | avg {1000 * total / count:7.2f} ms | max {1000 * maximum:7.2f} ms | n={count}"))
        for name in sorted(self._counters.keys()):
            lines.append((name, str(self._counters[name])))
        self._log_callback(title, lines)
        self._stages = {}
        self._counters = {}

    def report(self, reason: str = "window"):
        if not self.enabled or self._window_start_wall is None or self._iterations == 0:
            self._reset()
            return

        wall = time.perf_counter() - self._window_start_wall
        cpu = time.thread_time() - self._window_start_cpu
        if wall <= 0:
            self._reset()
            return

        lines: list[tuple[str, str]] = [
            ("iterations", f"{self._iterations} in {wall:.1f} s ({self._iterations / wall:.1f}/s)"),
            ("thread CPU", f"{cpu:.2f} s of {wall:.1f} s wall ({100 * cpu / wall:.0f}% of one core)"),
        ]
        for name in sorted(self._stages.keys()):
            count, total, maximum = self._stages[name]
            lines.append((name, f"avg {1000 * total / count:6.2f} ms | max {1000 * maximum:6.2f} ms | total {1000 * total:8.1f} ms | n={count}"))
        for name in sorted(self._counters.keys()):
            lines.append((name, str(self._counters[name])))

        self._log_callback(f"Painter timings ({reason})", lines)
        self._reset()
