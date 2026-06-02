from pyxavi import Dictionary, Config, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.xprocess_protocol import XprocessProtocol
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from pitxu.lib.objects import XprocAction

from multiprocessing import JoinableQueue, Process

class Xprocess(PyXavi, Process, XprocessProtocol):

    _PROCESS_NAME: str = "UNDEFINED_XPROCESS"

    _queue: JoinableQueue = None
    _output_queue: JoinableQueue = None
    _sentinel_output_queue: object = None
    _shared_memory: SharedMemoryManager = None
    _busy_flag: int = None

    _current_action: XprocAction = None

    def __init__(self, 
                 config: Config = None, 
                 params: Dictionary = None, 
                 queue: JoinableQueue = None, 
                 output_queue: JoinableQueue = None,
                 sentinel_output_queue: any = None,
                 busy_flag: int = None, **kwargs):

        self.init_pyxavi(config=config, params=params, **kwargs)

        self._PROCESS_NAME = self.get_process_name()
        self._xlog.debug("Initializing Xprocess [" + self._PROCESS_NAME + "]")

        if queue is None:
            raise ValueError("Xprocess [" + self._PROCESS_NAME + "] requires a JoinableQueue instance, got None.")
        self._queue = queue

        if output_queue is None:
            self._xlog.debug("Xprocess [" + self._PROCESS_NAME + "] has no output queue, continuing without it.")
        else:
            if sentinel_output_queue is None:
                raise ValueError("Xprocess [" + self._PROCESS_NAME + "] requires a sentinel_output_queue value when an output_queue is provided, got None.")
            self._output_queue = output_queue
            self._sentinel_output_queue = sentinel_output_queue

        # The busy flag is set in the XprocessPool when initializing the Process (see new() there)
        if busy_flag is None:
            raise ValueError("Xprocess [" + self._PROCESS_NAME + "] requires a busy_flag index, got None.")
        self._busy_flag = busy_flag

        super(Xprocess, self).__init__()

    def get_queue(self) -> JoinableQueue:
        return self._queue

    def get_output_queue(self) -> JoinableQueue:
        return self._output_queue

    def get_sentinel_output_queue(self) -> any:
        return self._sentinel_output_queue

    def get_busy_flag(self) -> int:
        return self._busy_flag

    def get_current_processing_action(self) -> XprocAction:
        return self._current_action

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
                self._log_debug("Xprocess [" + self._PROCESS_NAME + "] run() received a [" + action + (": " + self.ensure_nice_string(param) + "]" if param is not None else "]"))

                # Let's remember the current action
                self._current_action = action

                # We mark the process as busy
                self.set_busy()

                try:
                    # Run the context-aware run_with_context() first
                    self.run_with_context(self._xconfig, self._xlog, action, param)
                except NotImplementedError as e:
                    self._xlog.warning(f"🟠 NotImplementedError in Xprocess {self._PROCESS_NAME} run(). Will discard: {e}")

                # Executes the own do() passing the context.
                if action == XprocAction.DO:
                    self.do(self._xconfig, self._xlog, param)
                
                # Initializes the model from within the Process.
                # This is the only way to avoid Model Session issues
                if action == XprocAction.INITIALIZE:
                    self._log_debug("Performing the initialize() for process [" + self._PROCESS_NAME + "] from the SubProcess")
                    self.initialize()

                # We don't need to finish the subprocess from main explicitly, it will end when the job
                #   is done or when we call join() from main.
                # Still, we leave it so we have the tool for whatever other reason.
                if action == XprocAction.FINISH:
                    self._log_debug("Performing the finish() for process [" + self._PROCESS_NAME + "] from the SubProcess")
                    self.finish()
                
                # Removing the current action
                self._current_action = None
                
                # Finally, we mark this task as done
                self.mark_input_queue_task_as_done()

                # We're not busy anymore
                self.unset_busy()

        except KeyboardInterrupt:
            self._xlog.debug("Pressed Control + C while running Xprocess " + self._PROCESS_NAME + " run()")
            self.finish()
        except EOFError as e:
            self._xlog.error("🛑 EOFError detected in Xprocess " + self._PROCESS_NAME + " run(): " + str(e))
        except Exception as e:
            self._xlog.error("🛑 Unexpected Error in Xprocess " + self._PROCESS_NAME + " run(): " + str(e))
            self._xlog.debug(full_stack())
    
    def mark_input_queue_task_as_done(self):
        try:
            self._queue.task_done()
        except ValueError:
            pass
    
    def ensure_nice_string(self, value: any) -> str:
        try:
            # Assuming that a string longer than 10 characters that can be converted to int in base 16 is a hexadecimal value
            if type(value) == str and len(value) > 10:
                int(value, 16)
                return "<hexadecimal value>"
        except (ValueError, TypeError):
            pass
        return value if type(value) == str else str(type(value))


    def _initialize_on_every_run(self):
        '''
        Initialise something on every run() call.
        Called from run() before do()
        '''
        # Initialise config, logger, params
        self.init_pyxavi(config=self._xconfig, params=self._xparams)
        # Initialize shared memory
        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory_flags()

    def read_shared_memory_flag(self, index: int) -> bool:
        return self._shared_memory.read_shared_memory_flag(index)

    def write_shared_memory_flag(self, index: int, value: bool):
        self._shared_memory.write_shared_memory_flag(index, value)
    
    # Display busy control: is it already busy?
    def is_busy(self):
        return self.read_shared_memory_flag(self._busy_flag)
    
    # Display busy control: set as busy
    def set_busy(self):
        self.write_shared_memory_flag(self._busy_flag, True)

    # Display busy control: unset as busy
    def unset_busy(self):
        self.write_shared_memory_flag(self._busy_flag, False)