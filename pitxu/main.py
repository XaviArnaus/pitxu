from multiprocessing import set_start_method, JoinableQueue, Manager, shared_memory

from pyxavi import Logger, Config, Dictionary

import logging
import copy

from pitxu.lib.utils import Text, Stopwatch, Memory
from pitxu.lib.chatbot import GeminiChatbot
from pitxu.lib.eink import Display
from pitxu.lib.matrix_led import MatrixLed
from pitxu.lib.speech_to_text import Vosk
from pitxu.lib.text_to_speech import Piper
from pitxu.lib.dto import QueueItemType, QueueItemAction, QueueItemDisplay
from definitions import SHARED_MEMORY_NAME, SHARED_EINK_BUSY, SHARED_MATRIX_BUSY, SHARED_SPEAKER_BUSY


import sounddevice
import time
from queue import Empty

class Main:

    _xconfig: Config = None
    _xlog: logging = None

    _display: Display = None
    _matrix: MatrixLed = None
    _chatbot: GeminiChatbot = None
    _dictate: Vosk = None
    _speech: Piper = None

    _manager = None
    _queue_display: JoinableQueue = None
    _queue_matrix: JoinableQueue = None
    _queue_speech: JoinableQueue = None
    _shared_memory: shared_memory.ShareableList = None

    _stopwatch: Stopwatch = None
    _supported_languages: list = []
    _greeting_sentence: str = None
    _goodbye_sentence: str = None
    _exit_words: list = []

    COMM_DISPLAY = "display"
    COMM_MATRIX = "matrix"
    COMM_TTS = "tts"

    ENGLISH: str = "en-us"
    CATALAN: str = "ca"
    GERMAN: str = "de"
    SPANISH: str = "es"

    # Shared memory flag positions
    SHARED_SPEAKER_BUSY = 0
    SHARED_EINK_BUSY = 1
    SHARED_MATRIX_BUSY = 2

    def __init__(self, config: Config = None, params: Dictionary = None):

        # Possible runtime parameters
        self._xparams = params

        # Config is mandatory
        if config is None:
            raise RuntimeError("Config can not be None")
        self._xconfig = config

        # Common Logger
        self._xlog = Logger(config=config, base_path=params.get("base_path", "")).get_logger()
        self._xparams.set("logger", self._xlog)

        # Initial Language
        self._xparams.set("language", config.get("app.default_language", self.CATALAN))

        # Supported Languages
        self._supported_languages = config.get("languages.supported_languages")

        # Initialisating Shared Memory to handle execution flags between processes
        self._xparams.set("shared_memory_name", SHARED_MEMORY_NAME)
        self._shared_memory = shared_memory.ShareableList([
            False,  # speaker is busy (pause mic)
            False,  # e-ink is busy
            False,  # matrix is busy
        ], name=SHARED_MEMORY_NAME)
        if self._shared_memory is None:
            self._xlog.error("Shared Memory is None, cannot write flags")

        self._stopwatch = Stopwatch()
    
    def _initialize_multiprocess(self):
        # Some of the models will be hold in separate processes
        # Communication with them is done via a Queue
        self._manager = Manager()
        self._queue_display = self._manager.JoinableQueue()
        self._queue_speech = self._manager.JoinableQueue()
        self._queue_matrix = self._manager.JoinableQueue()

        # The `forkserver` method is the only one that allows to initialze the SoundDevice in the child thread
        # without issues. The `spawn` method fails when initializing the OutputStream, and `fork` is not
        # available in Mac.
        set_start_method('forkserver', force=True)  # For Mac M1/M2 compatibility. Works in RPi5

    def load_language(self, new_language: str):
        # Ensure that the language is supported
        if new_language not in self._supported_languages:
            raise RuntimeError("Language [" + new_language + "] is not supported")
        
        # Define the language to use
        self._xparams.set("language", new_language)

        # Reload the models now that we have a new language defined
        self._load_models()

        # Reload all language statics, like the exit words and the greeting / goodbye sentences
        self._load_language_statics()

    def _load_models(self):
        
        # Initialise Speech-to-Text
        self._xlog.debug("Initialising the Speech-to-Text with language [" + self._xparams.get("language") + "]")
        self._dictate = Vosk(config=self._xconfig, params=self._xparams)

        # Initialise Text-To-Speech. Please note that the object is a child of Process,
        #   so it only communicate with it via the queue.
        self._xlog.debug("Initialising the Text-to-Speech with language [" + self._xparams.get("language") + "]")
        tts_params = copy.deepcopy(self._xparams)
        tts_params.set("process_name", "TTS")
        self._speech = Piper(config=self._xconfig, params=tts_params, queue=self._queue_speech)
        self._speech.start()
        self._init_subprocess(who=QueueItemType.SPEECH)

        # Initialise Chatbot
        self._xlog.debug("Initialising the Chatbot Client with language [" + self._xparams.get("language") + "]")
        self._chatbot = GeminiChatbot(config=self._xconfig, params=self._xparams)
    
    def _load_language_statics(self):

        # Load the greeting sentence
        self._xlog.debug("Load Greeting with language [" + self._xparams.get("language") + "]")
        self._greeting_sentence = self._xconfig.get("language.greeting." + self._xparams.get("language"))

        # Load the goodbye sentence
        self._xlog.debug("Load Goodbye with language [" + self._xparams.get("language") + "]")
        self._goodbye_sentence = self._xconfig.get("language.goodbye." + self._xparams.get("language"))

        # Compile exit words
        all_possible_exit_words = []
        for language, exit_words in dict(self._xconfig.get("language.exit_words")).items():
            for word in exit_words:
                if word not in all_possible_exit_words:
                    all_possible_exit_words .append(word)
        self._xlog.debug("Load ALL possible exit words " + str(all_possible_exit_words) + "")
        self._exit_words = all_possible_exit_words
    
    def _initialize_displays(self):
        """
        Initialisation of the displays and macros
        """

        self._xlog.debug("Initialising Matrix LED Display and Macros")
        matrix_params = copy.deepcopy(self._xparams)
        matrix_params.set("process_name", "Matrix")
        self._matrix = MatrixLed(config=self._xconfig, params=matrix_params, queue=self._queue_matrix)
        self._matrix.start()
        self._init_subprocess(who=QueueItemType.MATRIX)
        # Needs an initial clear
        self._clear_matrix()

        self._xlog.debug("Initialising eInk Display and Macros")
        display_params = copy.deepcopy(self._xparams)
        display_params.set("process_name", "Display")
        self._display = Display(config=self._xconfig, params=display_params, queue=self._queue_display)
        self._display.start()
        self._init_subprocess(who=QueueItemType.DISPLAY)
    
    def run(self):

        sw_init = self._stopwatch.start(name="init")

        # Initialise Multiprocess components
        self._initialize_multiprocess()

        # Initialise eInk Display and the helper macros
        self._initialize_displays()

        # Startup splash. It should be understood as a "Loading..." screen.
        self._startup_splash()
        time.sleep(2)

        # Initialise all classes that require a model. They go per language, that's why it's abstracted
        self._load_models()

        # Reload all language statics, like the exit words and the greeting / goodbye sentences
        self._load_language_statics()

        self._xlog.debug("⏱️  Initialisations: " + str(self._stopwatch.stop(sw_init)))

        try:
            # Read from microphone
            # Correct format for Vosk is PCM 16khz 16bit mono
            with sounddevice.RawInputStream(samplerate=self._dictate.samplerate,
                                blocksize = 0, 
                                device=self._dictate.device,
                                dtype="int16", 
                                channels=1,
                                callback=self._dictate.callback) as input_stream:
                
                # Welcome greeting
                self._xlog.debug(">> Greetings")
                sw_greeting = self._stopwatch.start(name="greeting")
                self.communicate(self._greeting_sentence, [self.COMM_TTS, self.COMM_DISPLAY])
                self._xlog.debug("⏱️  Greeting: " + str(self._stopwatch.stop(sw_greeting)))

                question = ""
                dictate_count = 0
                answer_count = 0
                while(not self._text_has_exit_intention(question)):
                    try:
                        # Recognize what comes from the microphone
                        sw_dictate = self._stopwatch.continue_or_start(name="dictate" + str(dictate_count))
                        question = self._dictate.recognize()
                        if (question == None or question.strip() == ""):
                            continue
                        self._xlog.debug(">> Recognised dictate")
                        self._xlog.debug("⏱️  Dictate " + str(dictate_count) + ": " + str(self._stopwatch.stop(sw_dictate)))
                        dictate_count += 1

                        # Avoid calling the Chatbot when exiting
                        if self._text_has_exit_intention(question):
                            # Just assume a goodbye
                            answer = self._goodbye_sentence
                        else:
                            # Here we start with the Chatbot
                            answer = self._chatbot.ask(question)
                        
                        # Clean the answer first, just in case
                        answer = Text.remove_emojis(answer)
                        answer = Text.remove_markdown(answer)

                        # Answer
                        sw_answer = self._stopwatch.start(name="answer" + str(answer_count))
                        self.communicate(answer, [self.COMM_TTS, self.COMM_DISPLAY])
                        self._xlog.debug("⏱️  Answer " + str(answer_count) + ": " + str(self._stopwatch.stop(sw_answer)))
                        answer_count += 1
                    except KeyboardInterrupt:
                        break
                
                # We're here if the user said the exit words
                self.close_nicely()

        except KeyboardInterrupt:
            self._xlog.info("Pressed Control + C from main")
            self.close_nicely()
    
    def communicate(self, text: str, channels: list):
        """
        Communicates to the user using the channels defined.

        It is an abstraction to deliver in one shot display and audio (and whatever else in the future).
        It is a NOT blocking process, runs every channel in a separate process so they can run in parallel,
        speeding up the overall run.
        """

        # In case we want TTS, we need to pause the mic
        # this is done within the TTS process via a shared memory flag that tells the STT to pause

        if self.COMM_TTS in channels:
            # Say the answer
            self._xlog.debug("Say Communication")
            # We already have the TTS in a Process, listening for elements in the queue
            self._say(text)

        if self.COMM_DISPLAY in channels:
            # Show the answer
            self._xlog.debug("Show Communication")
            self._show(text)
        
        # We want that the main thread waits until some of the actions finished in the subprocesses
        self.wait_for_queue_to_empty(self._queue_display)
        self.wait_for_queue_to_empty(self._queue_speech)
        # Yeah, but still there is job to be done (speaking, for example)
        self.wait_for_busy_process_to_idle(SHARED_EINK_BUSY)
        self.wait_for_busy_process_to_idle(SHARED_SPEAKER_BUSY)
    
    def _text_has_exit_intention(self, text):
        return text in self._exit_words
    
    def close_nicely(self):
        sw_closing = self._stopwatch.continue_or_start(name="closing")
        self._xlog.debug("Closing nicely...")

        # Clean the displays
        self.clear_displays()

        # Wait for all the queues and processes to get empty
        self.wait_for_all_queues_to_empty()
        self.wait_for_all_busy_processes_to_idle()

        # Finish all related multiprocess stuff
        self.finish_leftover_processes()

        # ------ Final logs ------

        self._xlog.debug("We should be now nicely closed")
        self._xlog.debug("⏱️  Closed: " + str(self._stopwatch.stop(sw_closing)))

        # Here comes anything that we want to do before leaving
        self._xlog.info("⏱️  Final Stopwatch report:\n" + self._stopwatch.stop_and_report())
        self._xlog.info("💡  Memory used:" + str(Memory.use(Memory.MEGABYTES)) + " MB")
    
    def clear_displays(self):
        self._xlog.debug("Clearing the eInk.")
        self._clear_display()
        self._xlog.debug("Clearing the LED Matrix.")
        self._clear_matrix()
    
    def wait_for_all_queues_to_empty(self):
        # Now wait until the displays finish being busy
        self._xlog.debug("Waiting for all queues to get empty")
        self._xlog.debug("Current queues size: \n" +
                            "- eInk: " + str(self._queue_display.qsize()) + "\n" +
                            "- Matrix: " + str(self._queue_matrix.qsize()) + "\n" +
                            "- Speech: " + str(self._queue_speech.qsize()))
        # while self._shared_memory[SHARED_EINK_BUSY] and self._shared_memory[SHARED_MATRIX_BUSY]:
        sleep_seconds = 0.5
        total_sleeping = 0
        while self._queue_display.qsize() > 0\
            or self._queue_matrix.qsize() > 0\
            or self._queue_speech.qsize() > 0:
            total_sleeping += sleep_seconds
            time.sleep(sleep_seconds)

        self._xlog.debug("All queues are empty now. I've sleept " + str(total_sleeping) + "s.")
    
    def wait_for_queue_to_empty(self, queue: JoinableQueue):
        self._xlog.debug("Waiting for a queue to empty. Has now: " + str(queue.qsize()) + " elements.")
        sleep_seconds = 0.5
        total_sleeping = 0
        while queue.qsize() > 0:
            total_sleeping += sleep_seconds
            time.sleep(sleep_seconds)
        self._xlog.debug("The queue is empty now. I've sleept " + str(total_sleeping) + "s.")
    
    def wait_for_all_busy_processes_to_idle(self):
        # Now wait until the displays finish being busy
        self._xlog.debug("Waiting for all processes to get idle")
        self._xlog.debug("Current busy flags: \n" +
                            "- eInk: " + ("BUSY" if self._shared_memory[SHARED_EINK_BUSY] else "IDLE") + "\n" +
                            "- Matrix: " + ("BUSY" if self._shared_memory[SHARED_MATRIX_BUSY] else "IDLE") + "\n" +
                            "- Speech: " + ("BUSY" if self._shared_memory[SHARED_SPEAKER_BUSY] else "IDLE"))
        # while self._shared_memory[SHARED_EINK_BUSY] and self._shared_memory[SHARED_MATRIX_BUSY]:
        sleep_seconds = 0.5
        total_sleeping = 0
        while self._shared_memory[SHARED_EINK_BUSY]\
            or self._shared_memory[SHARED_MATRIX_BUSY]\
            or self._shared_memory[SHARED_SPEAKER_BUSY] > 0:
            total_sleeping += sleep_seconds
            time.sleep(sleep_seconds)

        self._xlog.debug("All processes are idle now. I've sleept " + str(total_sleeping) + "s.")
    
    def wait_for_busy_process_to_idle(self, memory_position: int):
        self._xlog.debug("Waiting for a process to idle. It's now: " + ("BUSY" if self._shared_memory[memory_position] else "IDLE") + ".")
        sleep_seconds = 0.5
        total_sleeping = 0
        while self._shared_memory[memory_position]:
            total_sleeping += sleep_seconds
            time.sleep(sleep_seconds)
        self._xlog.debug("The process is idle now. I've sleept " + str(total_sleeping) + "s.")



    def finish_leftover_processes(self):
        # We can't join() child processes unless all queues get totally consumed.

        # 1. Send a "finish" to the children. Needs the queue.
        # TODO: I believe that the issue is due to not waiting for this 'finish' to be read by the children
        #    from the queues. Maybe the main thread empties it before being read. 
        self._xlog.debug("[Main Finish] Send 'finish' to children")
        self._finish_subprocess()
        # ...so they can close dependencies.

        # 2. Clean and close the queues, apparently better from the one that put().
        self._xlog.debug("[Main Finish] Empty and close queues")
        self.clearAndDiscardQueue(self._queue_display)
        self.clearAndDiscardQueue(self._queue_matrix)
        self.clearAndDiscardQueue(self._queue_speech)
        # At this point the queues should be closed.

        # 3. Joining the queues to the main thread.
        self._xlog.debug("[Main Finish] Joining queues")
        self._queue_display.join()
        self._queue_matrix.join()
        self._queue_speech.join()

        # We don't need to ask the process to self-terminate. It will when it finishes the job.
        # self._queue.put((QueueItemType.ACTION,QueueItemAction.FINISH))
        self._xlog.debug("[Main Finish] Is the Speech subprocess still alive? " + ("Yes" if self._speech.is_alive() else "No"))
        if self._speech.is_alive():
            self._xlog.debug("[Main Finish] Terminating TTS Process")
            self._speech.terminate()
            # kill() does not fail (terminate() sometimes does), but appears to me pretty hardcode.
            # self._speech.kill()
        
        self._xlog.debug("[Main Finish] Is the Display subprocess still alive? " + ("Yes" if self._display.is_alive() else "No"))
        if self._display.is_alive():
            self._xlog.debug("[Main Finish] Terminating Display Process")
            self._display.terminate()
        
        self._xlog.debug("[Main Finish] Is the Matrix subprocess still alive? " + ("Yes" if self._matrix.is_alive() else "No"))
        if self._matrix.is_alive():
            self._xlog.debug("[Main Finish] Terminating Matrix Process")
            self._matrix.terminate()
        
        # Close the Shared Memory
        self._xlog.debug("[Main Finish] Closing Shared Memory")
        self._shared_memory.shm.close()
        self._shared_memory.shm.unlink()
    

    # ------- Communication with Queues ---------

    def _init_subprocess(self, who: QueueItemType = QueueItemType.ACTION):
        # Be aware that INITIALIZE and FINISH are managed within the subprocess itself,
        #   so who is always QueueItemType.ACTION to trigger them.

        if who == QueueItemType.ACTION:
            self._queue_speech.put((QueueItemType.ACTION, QueueItemAction.INITIALIZE))
            self._queue_display.put((QueueItemType.ACTION, QueueItemAction.INITIALIZE))
            self._queue_matrix.put((QueueItemType.ACTION, QueueItemAction.INITIALIZE))
        elif who == QueueItemType.DISPLAY:
            self._queue_display.put((QueueItemType.ACTION, QueueItemAction.INITIALIZE))
        elif who == QueueItemType.SPEECH:
            self._queue_speech.put((QueueItemType.ACTION, QueueItemAction.INITIALIZE))
        elif who == QueueItemType.MATRIX:
            self._queue_matrix.put((QueueItemType.ACTION, QueueItemAction.INITIALIZE))
        else:
            self._xlog.error("I can't understand who should I initialise: " + who)

    
    def _finish_subprocess(self, who: QueueItemType = QueueItemType.ACTION):
        # Be aware that INITIALIZE and FINISH are managed within the subprocess itself,
        #   so who is always QueueItemType.ACTION to trigger them.

        if who == QueueItemType.ACTION:
            self._queue_speech.put((QueueItemType.ACTION, QueueItemAction.FINISH))
            self._queue_display.put((QueueItemType.ACTION, QueueItemAction.FINISH))
            self._queue_matrix.put((QueueItemType.ACTION, QueueItemAction.FINISH))
        elif who == QueueItemType.DISPLAY:
            self._queue_display.put((QueueItemType.ACTION, QueueItemAction.FINISH))
        elif who == QueueItemType.SPEECH:
            self._queue_speech.put((QueueItemType.ACTION, QueueItemAction.FINISH))
        elif who == QueueItemType.MATRIX:
            self._queue_matrix.put((QueueItemType.ACTION, QueueItemAction.FINISH))
        else:
            self._xlog.error("I can't understand who should I finish: " + who)
    
    def _say(self, message: str):
        self._queue_speech.put((QueueItemType.SAY, message))
    
    def _show(self, message: str):
        self._queue_display.put((QueueItemType.SHOW, message))
        self._queue_matrix.put((QueueItemType.SHOW, message))
    
    def _startup_splash(self):
        self._queue_display.put((QueueItemType.DISPLAY, QueueItemDisplay.STARTUP))
        self.wait_for_queue_to_empty(self._queue_display)
    
    def _clear_display(self):
        # Now that we use partial refresh, the clear needs a previous white rectangle.
        # First a soft clear, so the screen is white
        self._queue_display.put((QueueItemType.DISPLAY, QueueItemDisplay.SOFT_CLEAR))
        # Full clear, to ensure a reset.
        self._queue_display.put((QueueItemType.DISPLAY, QueueItemDisplay.CLEAR))
    
    def _clear_matrix(self):
        self._queue_matrix.put((QueueItemType.MATRIX, QueueItemDisplay.CLEAR))

    def clearAndDiscardQueue(self, queue: JoinableQueue):
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