from multiprocessing import set_start_method, JoinableQueue, Manager
from queue import Empty
import time

from pyxavi import Config, Dictionary

from definitions import SHARED_EINK_BUSY, SHARED_MATRIX_BUSY, SHARED_SPEAKER_BUSY
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from pitxu.lib.objects import XprocAction


class XprocessPool(PyXavi):

    _manager = None
    _process: dict[str, Xprocess]
    _queue: dict[str, JoinableQueue]
    _shared_memory: SharedMemoryManager = None
    _shared_flags: dict[str, int] = {
        "eink_busy": SHARED_EINK_BUSY,
        "matrix_busy": SHARED_MATRIX_BUSY,
        "speaker_busy": SHARED_SPEAKER_BUSY,
    }   

    def __init__(self, config: Config, params: Dictionary):

        # Initialize the PyXavi parent
        self.init_pyxavi(config=config, params=params)

        # Initialize the process and queue dictionaries
        self._process = {}
        self._queue = {}

        # Initialize shared memory
        self._shared_memory = SharedMemoryManager(config=config, params=params)
        self._shared_memory.initialize_new_shared_memory()

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
    
    def add_and_start(self, name: str, process: Xprocess):
        self.add(name, process)
        self._xlog.debug("Starting process [" + name + "] from the pool")
        self._process[name].start()
        self.send(name, XprocAction.INITIALIZE)
    
    def new(self, name: str, target):
        self._xlog.debug("Creating and adding process [" + name + "] to the pool")
        if name in self._process:
            self._xlog.warning("process [" + name + "] already exists in the pool. Overwriting.")
        
        queue = self._manager.JoinableQueue()
        self._queue[name] = queue
        self._process[name] = target(config=self._xconfig, params=self._xparams, queue=queue)
    
    def new_and_start(self, name: str, target):
        self.new(name, target)
        self._xlog.debug("Starting process [" + name + "] from the pool")
        self._process[name].start()
        self.send(name, XprocAction.INITIALIZE)

    def get_process(self, name: str):
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
            self._queue[queue_name].put((action, param))
        else:
            self._xlog.error("queue [" + queue_name + "] does not exist in the pool.")

    def broadcast(self, action: XprocAction, param: str = None):
        for queue_name in self._queue.keys():
            self.send(queue_name, action, param)
    
    def wait_for_all_queues_to_empty(self):
        # Now wait until the displays finish being busy
        self._xlog.debug("Waiting for all queues to get empty")
        queue_sizes = "Current queues size: \n"
        for name, queue in self._queue.items():
            queue_sizes += "- " + name + ": " + str(queue.qsize()) + "\n"
        self._xlog.debug(queue_sizes)
        sleep_seconds = 0.5
        total_sleeping = 0
        while any(queue.qsize() > 0 for queue in self._queue.values()):
            total_sleeping += sleep_seconds
            time.sleep(sleep_seconds)
        self._xlog.debug("All queues are empty now. I've sleept " + str(total_sleeping) + "s.")
    
    def wait_for_queue_to_empty(self, queue_name: str):
        self._xlog.debug("Waiting for queue " + queue_name + " to empty. Has now: " + str(self.get_queue(queue_name).qsize()) + " elements.")
        sleep_seconds = 0.5
        total_sleeping = 0
        while self.get_queue(queue_name).qsize() > 0:
            total_sleeping += sleep_seconds
            time.sleep(sleep_seconds)
        self._xlog.debug("The queue " + queue_name + " is empty now. I've sleept " + str(total_sleeping) + "s.")
    
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
            self._clearAndDiscardQueue(queue)
        # At this point the queues should be closed.

        # 3. Joining the queues to the main thread.
        self._xlog.debug("Joining queues")
        for name, queue in self._queue.items():
            queue.join()

        # 4. Terminate any leftover processes
        for name, process in self._process.items():
            self._xlog.debug("[Main Finish] Is the subprocess [" + name + "] still alive? " + ("Yes" if process.is_alive() else "No"))
            if process.is_alive():
                self._xlog.debug("[Main Finish] Terminating Process [" + name + "]")
                process.terminate()
        
        # Close the Shared Memory
        self._xlog.debug("[Main Finish] Closing Shared Memory")
        self._shared_memory.close()
    
    def _clearAndDiscardQueue(self, queue: JoinableQueue):
        '''
        Queue cleanup, preferably in the process that is adding to the queue
        https://stackoverflow.com/a/69781217/1973860
        '''

        try:
            while True:
                queue.get_nowait()
        except Empty:
            pass    
        except ValueError:  # in case of closed
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

