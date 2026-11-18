import os
import select
import socket
import threading

from definitions import SHARED_MEMORY_FLAGS


class Doorbell:
    """
    A way to tell another process "something changed in the shared memory", so it does not need to keep asking.

    The shared memory is attached by name, but the Python synchronisation primitives (Condition, Event)
    can only be handed to a process when it starts, and the shared memory is used from too many places for that.
    So the doorbell works the same way as the shared memory: by name. Each listener owns a Unix datagram socket
    at a well known path, and any process rings it by sending one byte to that path.

    Why a socket:
        - A ring that arrives while the listener is busy is kept by the OS, so it can not be lost between
          checking the shared memory and going to sleep. The next wait returns straight away.
        - The listener sleeps in the kernel: no thread wakes up while nothing changes.
        - Ringing is a non blocking syscall, that fails silently if nobody listens (yet, or any more).

    A ring is only a hint to check the shared memory: the listeners keep a timeout as a safety net,
    so a missed ring never leaves a change unattended for long.
    """

    # The listeners that exist. Writers ring all of them.
    BELL_MAIN_MONITOR: str = "main_monitor"
    BELL_PAINTER_MONITOR: str = "painter_monitor"
    # The waits of the Main process (flags to be idle/busy, queues to be empty). See DoorbellWaiter.
    BELL_WAITER: str = "waiter"
    BELLS: tuple[str, ...] = (BELL_MAIN_MONITOR, BELL_PAINTER_MONITOR, BELL_WAITER)

    # ⚠️ Not tempfile.gettempdir(): the macOS one is so long that the socket path exceeds the AF_UNIX limit (104).
    DIRECTORY: str = "/tmp"

    @staticmethod
    def is_enabled(component: str = None) -> bool:
        """
        The doorbell can be switched off with the environment variable PITXU_DOORBELL=0 (the children inherit it).
        Then nobody rings and the monitors poll the shared memory, like they did before the doorbell.
        It is meant for telling if a problem comes from it.

        A single listening component can be switched off with PITXU_DOORBELL_<COMPONENT>=0: "MONITORS" (the flag monitors)
        or "WAITER" (the waits of Main). To find out which one a problem comes from.
        """
        if os.environ.get("PITXU_DOORBELL", "1") == "0":
            return False
        if component is not None and os.environ.get(f"PITXU_DOORBELL_{component.upper()}", "1") == "0":
            return False
        return True

    @staticmethod
    def path_for(bell_name: str) -> str:
        return os.path.join(Doorbell.DIRECTORY, f"{SHARED_MEMORY_FLAGS}_{bell_name}.sock")


class DoorbellRinger:
    """
    The writer side. One per process is enough, see ring().
    """

    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self, bell_names: tuple[str, ...] = Doorbell.BELLS):
        self._paths = [Doorbell.path_for(name) for name in bell_names]
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        # Ringing must never block the writer: a full listener already has a ring waiting.
        self._socket.setblocking(False)

    @classmethod
    def get(cls) -> "DoorbellRinger | None":
        """
        The ringer of this process, created the first time. None if it can not be created: then nobody is rung,
        and the listeners fall back on their timeout.
        """
        if not Doorbell.is_enabled():
            return None
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    try:
                        cls._instance = DoorbellRinger()
                    except OSError:
                        return None
        return cls._instance

    def ring(self):
        for path in self._paths:
            try:
                self._socket.sendto(b"1", path)
            except OSError:
                # Nobody listens at that path (FileNotFound, ConnectionRefused), or the listener is full (BlockingIO).
                pass

    def close(self):
        try:
            self._socket.close()
        except OSError:
            pass


class DoorbellListener:
    """
    The side that sleeps until it is rung. Bind it BEFORE reading the state that it waits for to change.
    """

    def __init__(self, bell_name: str):
        self._bell_name = bell_name
        self._path = Doorbell.path_for(bell_name)
        self._socket = None
        self._closed = False

        # A previous run that did not finish leaves its file behind.
        try:
            os.unlink(self._path)
        except FileNotFoundError:
            pass

        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            self._socket.bind(self._path)
        except OSError:
            self._socket.close()
            self._socket = None
            raise

        # The identity of the file that we just created, to leave alone one that is not ours when closing.
        try:
            self._inode = os.stat(self._path).st_ino
        except OSError:
            self._inode = None

        # Non blocking for ever, and the sleeping is done with poll(): the mode of the socket is never changed after
        #   this point. Several threads may use the same listener (the waits of Main do), and a socket that switches
        #   between blocking with a timeout and non blocking, depending on which thread was the last to touch it,
        #   turns the waits of the others into loops that do not sleep.
        self._socket.setblocking(False)

    def wait(self, timeout: float) -> bool:
        """
        Sleeps until a ring or the timeout. All the rings that are waiting count as one.

        Returns:
            bool: True if it was rung, False if the timeout was reached.
        """
        sock = self._socket
        if sock is None:
            return False
        try:
            poller = select.poll()
            poller.register(sock.fileno(), select.POLLIN)
            if not poller.poll(max(0, int(timeout * 1000))):
                return False
            # Many rings count as one: the check that follows covers all of them.
            return self._drain(sock)
        except (OSError, ValueError):
            # Closed while waiting.
            if not self._closed:
                raise
            return False

    def drain(self):
        """
        Discards the rings that are waiting, without sleeping. To be done BEFORE checking the state that is waited for:
        a ring that arrives after the check is kept, so the next wait returns straight away.
        """
        sock = self._socket
        if sock is None:
            return
        try:
            self._drain(sock)
        except OSError:
            pass

    @staticmethod
    def _drain(sock) -> bool:
        """ Reads all the rings that are waiting. True if there was at least one. """
        got = False
        while True:
            try:
                sock.recv(64)
                got = True
            except BlockingIOError:
                return got

    def wake(self):
        """
        Rings itself, to leave a wait that is running in another thread (when closing).
        """
        ringer = DoorbellRinger((self._bell_name,))
        try:
            ringer.ring()
        finally:
            ringer.close()

    def close(self):
        self._closed = True
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        # Only if it is still our file: another instance may have taken the path over after we bound it
        #   (a restart where the old process was still closing), and then it is theirs.
        try:
            if self._inode is not None and os.stat(self._path).st_ino == self._inode:
                os.unlink(self._path)
        except OSError:
            pass
