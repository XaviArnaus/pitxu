import threading, time
from collections import deque
from typing import Callable

import numpy as np


class SpeakerLevelMeter:
    """
    Turns the audio about to be played into a 0.0 - 1.0 level stream (a VU meter), published in sync with the playback.

    - feed() is called right before the (blocking) write of each audio chunk to the output stream.
      It never blocks: it computes the level of every small slice of the chunk in one numpy pass
      and schedules them on the wall clock, starting now, shifted by latency_offset.
    - A daemon thread publishes each level when it is due, through the publish callable.
    - stop() must be called once the output stream has drained: it clears the schedule and publishes 0.

    The level uses a fixed dB window (floor_db .. ceil_db), independent of any dynamic threshold.
    """

    def __init__(self,
                 publish: Callable[[float], None],
                 slice_seconds: float = 0.03,
                 floor_db: float = -45.0,
                 ceil_db: float = -8.0,
                 latency_offset: float = 0.0,
                 attack: float = 0.6,
                 release: float = 0.2,
                 log: Callable[[str], None] = None):
        self._publish = publish
        self._log = log
        self._slice = slice_seconds
        self._floor = floor_db
        self._ceil = ceil_db
        self._offset = latency_offset
        self._attack = attack
        self._release = release

        self._smoothed = 0.0
        self._scheduled_until = 0.0
        self._schedule: deque = deque()
        self._cond = threading.Condition()
        self._closed = False
        self._thread: threading.Thread = None

    def feed(self, samples: np.ndarray, sample_rate: int):
        n = max(1, int(sample_rate * self._slice))
        usable = len(samples) // n * n
        if usable == 0:
            return

        blocks = samples[:usable].astype(np.float32).reshape(-1, n) / 32768.0
        rms = np.sqrt(np.mean(blocks ** 2, axis=1))
        db = 20 * np.log10(np.maximum(rms, 1e-6))
        raw = np.clip((db - self._floor) / (self._ceil - self._floor), 0.0, 1.0)

        # Tuning aid: the dBFS distribution of each chunk (one sentence), against the current window.
        # Good values are roughly: floor_db near the p10, ceil_db near the p95.
        if self._log is not None:
            p10, p50, p95 = np.percentile(db, [10, 50, 95])
            self._log(f"SpeakerLevelMeter chunk of {len(db)} slices: dBFS p10={p10:.1f} p50={p50:.1f} "
                      f"p95={p95:.1f} max={db.max():.1f} | window floor={self._floor} ceil={self._ceil} "
                      f"| mean raw level={raw.mean():.2f}")

        # If nothing was scheduled any more (a pause between sentences), the smoothing starts again from silence.
        if time.monotonic() > self._scheduled_until:
            self._smoothed = 0.0

        # Fast attack, slow release, so the bars jump up with the speech and fall gently.
        levels = []
        for x in raw:
            k = self._attack if x > self._smoothed else self._release
            self._smoothed += (float(x) - self._smoothed) * k
            levels.append(self._smoothed)

        base = max(time.monotonic(), self._scheduled_until)
        with self._cond:
            for i, level in enumerate(levels):
                self._schedule.append((base + i * self._slice + self._offset, level))
            self._scheduled_until = base + len(levels) * self._slice
            # When this audio ends, go back to silence. If the next chunk is scheduled right after it,
            # its first level is due at the same time and wins, so there is no flicker between sentences.
            self._schedule.append((self._scheduled_until + self._offset, 0.0))
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="SpeakerLevelMeter", daemon=True)
                self._thread.start()
            self._cond.notify()

    def stop(self):
        """To be called once the output stream has drained."""
        with self._cond:
            self._schedule.clear()
            self._scheduled_until = 0.0
            self._smoothed = 0.0
        self._publish(0.0)

    def close(self):
        with self._cond:
            self._closed = True
            self._cond.notify()
        self.stop()

    def _run(self):
        while True:
            with self._cond:
                if self._closed:
                    return
                if not self._schedule:
                    self._cond.wait()
                    continue
                wait = self._schedule[0][0] - time.monotonic()
                if wait > 0:
                    self._cond.wait(timeout=wait)
                    continue
                # Catch up: if several levels are already due, keep only the latest one.
                level = self._schedule.popleft()[1]
                while self._schedule and self._schedule[0][0] <= time.monotonic():
                    level = self._schedule.popleft()[1]
            self._publish(level)
