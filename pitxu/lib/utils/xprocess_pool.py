from multiprocessing import set_start_method, JoinableQueue, Manager
from queue import Empty
import time

from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.abstract.xprocess_display_background import XprocessDisplayBackground
from pitxu.lib.abstract.xprocess_display_foreground import XprocessDisplayForeground
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from pitxu.lib.objects import XprocAction
from definitions import SHARED_EINK_BUSY, SHARED_MATRIX_BUSY, SHARED_SPEAKER_BUSY, SHARED_LCD_BUSY, SHARED_DSI_LCD_BUSY, SHARED_SUPPORT_BUSY, \
                        QUEUE_EINK, QUEUE_MATRIX, QUEUE_SPEAKER, QUEUE_LCD, QUEUE_DSI_LCD, QUEUE_SUPPORT


class XprocessPool(PyXavi):

    _manager = None
    _process: dict[str, Xprocess]
    _queue: dict[str, JoinableQueue]
    _shared_memory: SharedMemoryManager = None

    # TODO: consider generating this map automatically together with shared_memory_manager, painter_busy_flags, etc.
    _shared_flags: dict[str, int] = {
        "eink_busy": SHARED_EINK_BUSY,
        "matrix_busy": SHARED_MATRIX_BUSY,
        "speaker_busy": SHARED_SPEAKER_BUSY,
        "lcd_busy": SHARED_LCD_BUSY,
        "dsi_lcd_busy": SHARED_DSI_LCD_BUSY,
        "support_busy": SHARED_SUPPORT_BUSY,
    }
    _shared_flags_per_queue: dict[str, str] = {
        QUEUE_EINK: SHARED_EINK_BUSY,
        QUEUE_MATRIX: SHARED_MATRIX_BUSY,
        QUEUE_SPEAKER: SHARED_SPEAKER_BUSY,
        QUEUE_LCD: SHARED_LCD_BUSY,
        QUEUE_DSI_LCD: SHARED_DSI_LCD_BUSY,
        QUEUE_SUPPORT: SHARED_SUPPORT_BUSY,
    }

    def __init__(self, config: Config, params: Dictionary):

        # Initialize the PyXavi parent
        super(XprocessPool, self).init_pyxavi(config=config, params=params)

        # Initialize the process and queue dictionaries
        self._process = {}
        self._queue = {}

        # Initialize shared memory
        self._shared_memory = SharedMemoryManager(config=config, params=params)
        self._shared_memory.initialize_new_shared_memory_flags()

        # Initialise the manager that will create the queues
        self._manager = Manager()

        # The `forkserver` method is the only one that allows to initialze the SoundDevice in the child thread
        # without issues. The `spawn` method fails when initializing the OutputStream, and `fork` is not
        # available in Mac.
        set_start_method('forkserver', force=True)  # For Mac M1/M2 compatibility. Works in RPi5

    def add(self, name: str, process: Xprocess):
        self._xlog.debug("Adding process [" + name + "] to the pool")
        if name in self._process:
            self._xlog.warning("process [" + name + "] already exists in the pool. Overwriting.")
        self._process[name] = process
        self._queue[name] = process.get_queue()

    def add_and_start(self, name: str, process: Xprocess, params: Dictionary = None):
        self.add(name, process)
        self.start(name)

        if params is not None and params.get("initialize_from_main", True) is True:
            self.initialize_from_main(name)
    
    def new(self, name: str, target, params: Dictionary = None) -> dict | None:
        self._xlog.debug("Creating and adding process [" + name + "] to the pool")
        if name in self._process:
            self._xlog.warning("process [" + name + "] already exists in the pool. Overwriting.")
        
        if params is None:
            params = Dictionary()
        
        output_queue = None
        sentinel_output_queue = None
        if params.key_exists("use_output_queue") and params.get("use_output_queue") is True:
            output_queue = self._manager.JoinableQueue()
            sentinel_output_queue = object()  # A unique value to signal the end of the output queue stream
        
        queue = self._manager.JoinableQueue()
        self._queue[name] = queue
        self._process[name] = target(
            config=self._xconfig, 
            params=self._xparams.merge(origin=params), 
            queue=queue,
            output_queue=output_queue,
            sentinel_output_queue=sentinel_output_queue,
            busy_flag=self._shared_flags_per_queue.get(name, None)
        )

        if output_queue is not None:
            return {
                "output_queue": output_queue,
                "sentinel_output_queue": sentinel_output_queue
            }
        else:
            return None

    def new_and_start(self, name: str, target, params: Dictionary = None) -> dict | None:
        output_queue_params = self.new(name, target, params=params)
        self.start(name)

        if params is not None and params.get("initialize_from_main", True) is True:
            self.initialize_from_main(name)
        
        return output_queue_params
    
    def start(self, name: str):
        if name in self._process:
            self._xlog.debug("Starting process [" + name + "] from the pool")
            self._process[name].start()
            self.send(name, XprocAction.INITIALIZE)
        else:
            self._xlog.error("process [" + name + "] does not exist in the pool.")
    
    def initialize_from_main(self, name: str):
        if name in self._process:
            self._xlog.debug("Performing the initialize_from_main_process() for process [" + name + "] from the main Process")
            self._process[name].initialize_from_main_process()
        else:
            self._xlog.error("process [" + name + "] does not exist in the pool.")

    def get_process(self, name: str) -> Xprocess | XprocessDisplayBackground | XprocessDisplayForeground | None:
        if name in self._process:
            return self._process[name]
        else:
            self._xlog.error("process [" + name + "] does not exist in the pool.")
            return None
    
    def get_queue(self, name: str):
        if name in self._queue:
            return self._queue[name]
        else:
            self._xlog.error("queue [" + name + "] does not exist in the pool.")
            return None
    
    def remove(self, name: str):
        if name in self._process:
            self._xlog.debug("Removing process and queue [" + name + "] from the pool")
            del self._process[name]
            del self._queue[name]
        else:
            self._xlog.error("process [" + name + "] does not exist in the pool.")
    
    def list(self) -> list[str]:
        return list(self._process.keys())
    
    def send(self, queue_name: str, action: XprocAction, param: str = None):
        if queue_name in self._queue:
            try:
                self._queue[queue_name].put((action, param))
            except BrokenPipeError as e:
                self._xlog.error("Queue [" + queue_name + "] is in BrokenPipe state " + str(e))
            except ConnectionResetError as e:
                self._xlog.error("Queue [" + queue_name + "] is in ConnectionReset state " + str(e))
        else:
            self._xlog.error("queue [" + queue_name + "] does not exist in the pool.")

    def broadcast(self, action: XprocAction, param: str = None):
        for queue_name in self._queue.keys():
            self.send(queue_name, action, param)

    def get_memory_manager(self) -> SharedMemoryManager:
        return self._shared_memory
    
    def wait_for_all_queues_to_empty(self):
        # Now wait until the displays finish being busy
        self._xlog.debug("Waiting for all queues to get empty")
        logging_queue_sizes = []
        queues_to_wait_for = []
        for name, queue in self._queue.items():
            try:
                logging_queue_sizes.append((name,str(queue.qsize()) + " elements"))
                queues_to_wait_for.append(queue)
            except BrokenPipeError:
                logging_queue_sizes.append((name, "BrokenPipeError"))
                self.reset_busy_flag_from_related_queue(name)
        self.log_summary(
            "Current queues sizes",
            logging_queue_sizes
        )
        sleep_seconds = 0.5
        total_sleeping = 0
        while any(queue.qsize() > 0 for queue in queues_to_wait_for):
            total_sleeping += sleep_seconds
            time.sleep(sleep_seconds)
        self._xlog.debug("All queues are empty now. I've sleept " + str(total_sleeping) + "s.")
    
    def wait_for_queue_to_empty(self, queue_name: str):
        if self.get_queue(queue_name) is None:
            self._xlog.error("Queue " + queue_name + " does not exist. Cannot wait for it to empty. I'll continue.")
            return
        try:
            self._xlog.debug("Waiting for queue " + queue_name + " to empty. Has now: " + str(self.get_queue(queue_name).qsize()) + " elements.")
        except BrokenPipeError:
            self._xlog.error("Queue " + queue_name + " BrokenPipeError when checking size. Cannot wait for it to empty. I'll continue.")
            self.reset_busy_flag_from_related_queue(queue_name)
            return
        sleep_seconds = 0.5
        total_sleeping = 0
        while self.get_queue(queue_name).qsize() > 0:
            total_sleeping += sleep_seconds
            time.sleep(sleep_seconds)
        self._xlog.debug("The queue " + queue_name + " is empty now. I've sleept " + str(total_sleeping) + "s.")
    
    def reset_busy_flag_from_related_queue(self, queue: str):
        if queue not in self._shared_flags_per_queue:
            self._xlog.error(f"Queue {queue} does not have a related shared flag. Cannot reset busy flag.")
            return
        flag_name = self._shared_flags_per_queue[queue]
        self._xlog.debug(f"Resetting busy flag {flag_name} related to queue {queue}")
        self._shared_memory.write_shared_memory_flag(flag_name, False)
    
    def get_busy_flag_from_related_queue(self, queue: str) -> int:
        if queue not in self._shared_flags_per_queue:
            self._xlog.error(f"Queue {queue} does not have a related shared flag. Cannot get busy flag.")
            return -1
        return self._shared_flags_per_queue[queue]
    
    def finish_leftover_processes(self):
        # We can't join() child processes unless all queues get totally consumed.

        # 1. Send a "finish" to the children. Needs the queue.
        # TODO: I believe that the issue is due to not waiting for this 'finish' to be read by the children
        #    from the queues. Maybe the main thread empties it before being read. 
        self._xlog.debug("Send 'finish' to children")
        self.broadcast(XprocAction.FINISH)
        # ...so they can close dependencies.

        # 2. Clean and close the queues, apparently better from the one that put().
        self._xlog.debug("Empty and close queues")
        for name, queue in self._queue.items():
            if queue is not None:
                self.force_queue_to_empty(queue)
        # At this point the queues should be closed.

        # 3. Joining the queues to the main thread.
        self._xlog.debug("Joining queues")
        for name, queue in self._queue.items():
            if queue is not None:
                try:
                    queue.join()
                except BrokenPipeError:  # in case of closed
                    pass

        # 4. Terminate any leftover processes
        for name, process in self._process.items():
            self._xlog.debug("Is the subprocess [" + name + "] still alive? " + ("Yes" if process.is_alive() else "No"))
            if process.is_alive():
                self._xlog.debug("Terminating Process [" + name + "]")
                process.terminate()
        
        # Close the Shared Memory Manager
        self._xlog.debug("Closing Shared Memory Manager")
        self._shared_memory.close()
    
    def force_queue_to_empty(self, queue: JoinableQueue):
        '''
        Queue cleanup, preferably in the process that is adding to the queue
        https://stackoverflow.com/a/69781217/1973860
        ---
        This method will attempt to empty the queue by removing all items and marking them as done.
        '''

        try:
            while True:
                queue.get_nowait()
        except Empty:
            pass    
        except ValueError:  # in case of closed
            pass
        except BrokenPipeError:  # in case of closed
            pass
        # queue.close()
        # theoretically a new item could be placed by the
        # other process by the time the interpreter is on this line,
        # therefore the part above should be run in the process that 
        # fills (put) the queue when it is in its failure state
        # (when the main process fails it should communicate to
        # raise an exception in the child process to run the cleanup
        # so main process' join will work)
        try: # could be one of the processes
            while True:
                queue.task_done()
        except ValueError:  # too many times called, do not care
        #  since all remaining will not be processed due to failure state
            pass
        except BrokenPipeError:  # in case of closed
            pass

