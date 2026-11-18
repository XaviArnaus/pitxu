
from pyxavi import Config, Dictionary

from pitxu.lib.core.shared_memory_monitor import SharedMemoryMonitor

class PainterSharedMemory(SharedMemoryMonitor):
    """
    The shared memory monitoring of the Painter.

    All the monitoring (flags, values, dependant callbacks, the worker) is in SharedMemoryMonitor.
    This only adds that, whenever the worker triggers any callback, the painter loop is resumed,
    to ensure that the interaction is painted as soon as possible.
    """

    # The Painter's resume function.
    _painter_resume_callback: callable = None

    THREAD_NAME: str = "PainterSharedMemory"

    def __init__(self, config: Config, params: Dictionary):
        if not params.key_exists("painter_resume_callback"):
            raise ValueError("PainterSharedMemory requires a painter_resume_callback to be provided in the params. Got None.")

        # ⚠️ It must be set BEFORE the parent initialisation, as that one starts the worker thread,
        #   and the worker may trigger the hook straight away.
        self._painter_resume_callback = params.get("painter_resume_callback")

        super(PainterSharedMemory, self).__init__(config, params)

    def _after_callbacks_triggered(self):
        self._log_debug("🚩  Resuming painter loop after triggering callbacks for shared memory flags or values.")
        self._painter_resume_callback()
