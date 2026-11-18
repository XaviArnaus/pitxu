import multiprocessing
import threading
import time

from pitxu.lib.core.doorbell import Doorbell, DoorbellListener


class DoorbellWaiter:
    """
    Waits for a condition on the shared memory or the queues (a flag to be idle, a queue to be empty...)
    sleeping until the doorbell rings instead of asking again every few milliseconds.

    Only the Main process waits like this: it owns the listener. Any other process (children, the manager)
    falls back on polling, as binding the socket there would take it away from Main.

    A ring is only a hint to check again: if nobody rings (a queue without a busy flag, a different thread
    that consumed the ring, the doorbell disabled) the condition is still checked at the safety timeout.
    """

    _listener: DoorbellListener | None = None
    _listener_lock = threading.Lock()
    _listener_unavailable: bool = False

    @classmethod
    def _get_listener(cls) -> DoorbellListener | None:
        if cls._listener_unavailable or not Doorbell.is_enabled():
            return None
        # ⚠️ Binding unlinks whatever is at the path: only Main may do it.
        if multiprocessing.parent_process() is not None:
            return None
        if cls._listener is None:
            with cls._listener_lock:
                if cls._listener is None and not cls._listener_unavailable:
                    try:
                        cls._listener = DoorbellListener(Doorbell.BELL_WAITER)
                    except OSError:
                        cls._listener_unavailable = True
        return cls._listener

    @classmethod
    def wait_until(
        cls,
        condition: callable,
        timeout: float | None = None,
        safety_seconds: float = 0.1,
        polling_seconds: float = 0.01,
    ) -> bool:
        """
        Waits until condition() is true.

        Args:
            condition: Returns True when what we wait for happened. It may be slow or raise: it is the caller's.
            timeout: Seconds to give up. None waits forever.
            safety_seconds: With the doorbell, the longest sleep between two checks if nobody rings.
            polling_seconds: Without the doorbell, the sleep between two checks.

        Returns:
            bool: True if the condition was met, False if the timeout was reached.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        listener = cls._get_listener()

        while True:
            if listener is not None:
                # Before the check: what rings after it stays queued and the wait below returns at once.
                listener.drain()
            if condition():
                return True

            sleep_seconds = safety_seconds if listener is not None else polling_seconds
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                sleep_seconds = min(sleep_seconds, remaining)

            if listener is not None:
                try:
                    listener.wait(sleep_seconds)
                except Exception:
                    # Whatever it is, from now on this wait polls.
                    listener = None
            else:
                time.sleep(sleep_seconds)

    @classmethod
    def close(cls):
        with cls._listener_lock:
            if cls._listener is not None:
                cls._listener.close()
                cls._listener = None
            # Anything waiting from now on polls.
            cls._listener_unavailable = True
