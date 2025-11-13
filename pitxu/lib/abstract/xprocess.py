from pyxavi import Dictionary, Config
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.xprocess_protocol import XprocessProtocol
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from pitxu.lib.dto import QueueItemType, QueueItemAction

from multiprocessing import JoinableQueue, shared_memory, Process

class Xprocess(PyXavi, Process, XprocessProtocol):

    _PROCESS_NAME: str = "UNDEFINED_XPROCESS"

    _queue: JoinableQueue = None
    _shared_memory: shared_memory.ShareableList = None

    def __init__(self, config: Config = None, params: Dictionary = None, queue: JoinableQueue = None, **kwargs):
        self.init_pyxavi(config=config, params=params, **kwargs)

        self._PROCESS_NAME = self.get_process_name()
        self._xlog.debug("Initializing Xprocess [" + self._PROCESS_NAME + "]")

        self._queue = queue

        super(Xprocess, self).__init__()

    def get_queue(self) -> JoinableQueue:
        return self._queue

    def run(self):
        '''
        Managed by Process
        Gets called whenever the self._queue.put() is called from the main.py
        '''
        try:
            # Apparently the parent Process class has a run() implementation,
            # but I don't see the difference in behaviour.
            super(Xprocess, self).run()

            # Initialisations needed on every run
            self._initialize_on_every_run()

            self._xlog.debug("Xprocess [" + self._PROCESS_NAME + "] run()")
            for queue_item in iter(self._queue.get, None):
                type, message = queue_item
                self._xlog.debug("Xprocess [" + self._PROCESS_NAME + "] run() received a [" + type + "]: [" + message + "]")

                # This is the old way, to be deprecated
                self.run_with_context(self._xconfig, self._xlog, type, message)

                # Executes the own do() passing the context.
                if type == QueueItemType.DO:
                    self.do(self._xconfig, self._xlog, message)
                
                # Initializes the model from within the Process.
                # This is the only way to avoid Model Session issues
                if type == QueueItemType.ACTION and message == QueueItemAction.INITIALIZE:
                    self.initialize()

                # We don't need to finish the subprocess from main explicitly, it will end when the job
                #   is done or when we call join() from main.
                # Still, we leave it so we have the tool for whatever other reason.
                if type == QueueItemType.ACTION and message == QueueItemAction.FINISH:
                    self.finish()
                
                # Finally, we mark this task as done
                self._queue.task_done()

        except KeyboardInterrupt:
            self._xlog.debug("Pressed Control + C while running Xprocess run()")
            self.finish()

    def _initialize_on_every_run(self):
        '''
        Initialise something on every run() call.
        Called from run() before do()
        '''
        # Initialise config, logger, params
        self.init_pyxavi(config=self._xconfig, params=self._xparams)
        # Initialize shared memory
        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory()

    def read_shared_memory_flag(self, index: int) -> bool:
        return self._shared_memory.read_shared_memory_flag(index)

    def write_shared_memory_flag(self, index: int, value: bool):
        self._shared_memory.write_shared_memory_flag(index, value)
