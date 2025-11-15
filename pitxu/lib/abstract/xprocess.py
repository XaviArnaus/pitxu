from pyxavi import Dictionary, Config, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.xprocess_protocol import XprocessProtocol
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from pitxu.lib.objects import XprocAction

from multiprocessing import JoinableQueue, Process

class Xprocess(PyXavi, Process, XprocessProtocol):

    _PROCESS_NAME: str = "UNDEFINED_XPROCESS"

    _queue: JoinableQueue = None
    _shared_memory: SharedMemoryManager = None

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
        '''
        try:
            # Apparently the parent Process class has a run() implementation,
            # but I don't see the difference in behaviour.
            super(Xprocess, self).run()

            # Initialisations needed on every run
            self._initialize_on_every_run()

            self._xlog.debug("Xprocess [" + self._PROCESS_NAME + "] run()")
            for queue_item in iter(self._queue.get, None):
                action, param = queue_item
                self._xlog.debug("Xprocess [" + self._PROCESS_NAME + "] run() received a [" + action + (": " + param + "]" if param is not None else "]"))

                # This is the old way, to be deprecated
                self.run_with_context(self._xconfig, self._xlog, action, param)

                # Executes the own do() passing the context.
                if action == XprocAction.DO:
                    self.do(self._xconfig, self._xlog, param)
                
                # Initializes the model from within the Process.
                # This is the only way to avoid Model Session issues
                if action == XprocAction.INITIALIZE:
                    self.initialize()

                # We don't need to finish the subprocess from main explicitly, it will end when the job
                #   is done or when we call join() from main.
                # Still, we leave it so we have the tool for whatever other reason.
                if action == XprocAction.FINISH:
                    self.finish()
                
                # Finally, we mark this task as done
                try:
                    self._queue.task_done()
                except ValueError:
                    pass

        except KeyboardInterrupt:
            self._xlog.debug("Pressed Control + C while running Xprocess " + self._PROCESS_NAME + " run()")
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
