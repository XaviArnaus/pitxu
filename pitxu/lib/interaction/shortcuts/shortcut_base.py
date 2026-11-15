from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.core.xprocess_pool import XprocessPool

class ShortcutBase(PyXavi):

    display_queue: str = None

    # Subprocess control
    process_pool: XprocessPool = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(ShortcutBase, self).init_pyxavi(config=config, params=params)

        self._xlog.info("Initializing Foreground interaction shortcuts.")

        # All interactions will be done via processes
        if params.key_exists("process_pool"):
            self.process_pool = params.get("process_pool")
        else:
            raise ValueError("Missing 'process_pool' parameter")
        
        # Important to get the display_queue
        if params.key_exists("display_queue"):
            self.display_queue = params.get("display_queue")
        else:
            raise ValueError("Missing 'display_queue' parameter")
    
    def close(self):
        """
        Close the Background interaction shortcuts.
        """
        self._xlog.debug("Closing Background interaction shortcuts.")

        self.process_pool.get_memory_manager().force_all_flags_to_idle(is_closing=True)
    
    # --------- Helper functions ---------

    def get_queue(self):
        """
        Get the active background display queue.

        Returns:
            str: The queue name of the active background display.
        """
        return self.display_queue
    
    def get_display_busy_flag(self):
        """
        Get the active background display busy flag.

        Returns:
            str: The busy flag name of the active background display.
        """
        return self.process_pool.get_busy_flag_from_related_queue(self.get_queue())