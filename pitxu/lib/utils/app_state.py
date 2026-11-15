import threading

from pyxavi import Config, Dictionary, Storage

from pitxu.lib.abstract.pyxavi import PyXavi


class AppState(PyXavi):
    """
    The ONE persistent state of the application (the state file): language, tokens counter...

    Created once by Main and shared by everyone that needs it (Reactions, ...), so there is a single
    in-memory copy. Several `Storage` instances on the same file overwrite each other with stale data.

    - Only persistent data goes here. Runtime readings (battery, temperature...) live in the shared memory values,
      published by the DeviceMonitor.
    - set() writes the file only when the value changed.
    - It is thread safe: the scheduler's threads and the main thread use it.
    """

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(AppState, self).init_pyxavi(config=config, params=params)

        self._lock = threading.RLock()
        self._storage = Storage(filename=self._xconfig.get("storage.path") + self._xconfig.get("storage.state_file"))

    def get(self, key: str, default: any = None) -> any:
        with self._lock:
            return self._storage.get(key, default)

    def set(self, key: str, value: any) -> bool:
        """
        Sets the value and persists it, only if it changed.

        Returns:
            True if it changed (and was written), False otherwise.
        """
        with self._lock:
            if self._storage.key_exists(key) and self._storage.get(key) == value:
                return False
            self._storage.set(key, value)
            self._storage.write_file()
            return True

    def flush(self):
        """
        Writes the file now, changed or not.
        """
        with self._lock:
            self._storage.write_file()
