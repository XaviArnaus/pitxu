from multiprocessing import set_start_method, JoinableQueue, Manager, shared_memory

from pyxavi import Logger, Config, Dictionary

import logging

from pitxu.lib.utils import Text, Stopwatch, Memory
from pitxu.lib.chatbot import GeminiChatbot
from pitxu.lib.eink import DisplayMultiprocess
from pitxu.lib.matrix_led import Matrix
from pitxu.lib.speech_to_text import Vosk
from pitxu.lib.text_to_speech import PiperMultiprocess
from pitxu.lib.dto import QueueItemType, QueueItemAction, QueueItemDisplay
from definitions import SHARED_MEMORY_NAME, SHARED_EINK_BUSY, SHARED_MATRIX_BUSY


import sounddevice
import time
from queue import Empty

class Main:

    _config: Config = None
    _logger: logging = None

    _display: DisplayMultiprocess = None
    _matrix: Matrix = None
    _chatbot: GeminiChatbot = None
    _dictate: Vosk = None
    _speech: PiperMultiprocess = None

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
        self._parameters = params

        # Config is mandatory
        if config is None:
            raise RuntimeError("Config can not be None")
        self._config = config

        # Common Logger
        self._logger = Logger(config=config, base_path=params.get("base_path", "")).get_logger()
        self._parameters.set("logger", self._logger)

        # Initial Language
        self._parameters.set("language", config.get("app.default_language", self.CATALAN))

        # Supported Languages
        self._supported_languages = config.get("languages.supported_languages")

        # Initialisating Shared Memory to handle execution flags between processes
        self._parameters.set("shared_memory_name", SHARED_MEMORY_NAME)
        self._shared_memory = shared_memory.ShareableList([
            False,  # speaker is busy (pause mic)
            False,  # e-ink is busy
            False,  # matrix is busy
        ], name=SHARED_MEMORY_NAME)
        if self._shared_memory is None:
            self._logger.error("Shared Memory is None, cannot write flags")

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
        self._parameters.set("language", new_language)

        # Reload the models now that we have a new language defined
        self._load_models()

        # Reload all language statics, like the exit words and the greeting / goodbye sentences
        self._load_language_statics()

    def _load_models(self):
        
        # Initialise Speech-to-Text
        self._logger.debug("Initialising the Speech-to-Text with language [" + self._parameters.get("language") + "]")
        self._dictate = Vosk(self._config, params=self._parameters)

        # Initialise Text-To-Speech. Please note that the object is a child of Process,
        #   so it only communicate with it via the queue.
        self._logger.debug("Initialising the Text-to-Speech with language [" + self._parameters.get("language") + "]")
        self._speech = PiperMultiprocess(self._config, params=self._parameters, queue=self._queue_speech)
        self._speech.start()
        self._init_subprocess(who=QueueItemType.SPEECH)

        # Initialise Chatbot
        self._logger.debug("Initialising the Chatbot Client with language [" + self._parameters.get("language") + "]")
        self._chatbot = GeminiChatbot(config=self._config, params=self._parameters)
    
    def _load_language_statics(self):

        # Load the greeting sentence
        self._logger.debug("Load Greeting with language [" + self._parameters.get("language") + "]")
        self._greeting_sentence = self._config.get("language.greeting." + self._parameters.get("language"))

        # Load the goodbye sentence
        self._logger.debug("Load Goodbye with language [" + self._parameters.get("language") + "]")
        self._goodbye_sentence = self._config.get("language.goodbye." + self._parameters.get("language"))

        # Compile exit words
        all_possible_exit_words = []
        for language, exit_words in dict(self._config.get("language.exit_words")).items():
            for word in exit_words:
                if word not in all_possible_exit_words:
                    all_possible_exit_words .append(word)
        self._logger.debug("Load ALL possible exit words " + str(all_possible_exit_words) + "")
        self._exit_words = all_possible_exit_words
    
    def _initialize_displays(self):
        """
        Initialisation of the displays and macros
        """

        self._logger.debug("Initialising eInk Display and Macros")
        self._display = DisplayMultiprocess(config=self._config, params=self._parameters, queue=self._queue_display)
        self._display.start()
        self._init_subprocess(who=QueueItemType.DISPLAY)

        self._logger.debug("Initialising Matrix LED Display and Macros")
        self._matrix = Matrix(config=self._config, params=self._parameters, queue=self._queue_matrix)
        self._matrix.start()
        self._init_subprocess(who=QueueItemType.MATRIX)
    
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

        self._logger.debug("⏱️  Initialisations: " + str(self._stopwatch.stop(sw_init)))

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
                self._logger.debug(">> Greetings")
                sw_greeting = self._stopwatch.start(name="greeting")
                self.communicate(self._greeting_sentence,
                                 [self.COMM_TTS, self.COMM_DISPLAY])
                self._logger.debug("⏱️  Greeting: " + str(self._stopwatch.stop(sw_greeting)))

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
                        self._logger.debug(">> Recognised dictate")
                        self._logger.debug("⏱️  Dictate " + str(dictate_count) + ": " + str(self._stopwatch.stop(sw_dictate)))
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
                        self._logger.debug("⏱️  Answer " + str(answer_count) + ": " + str(self._stopwatch.stop(sw_answer)))
                        answer_count += 1
                    except KeyboardInterrupt:
                        break
                
                # We're here if the user said the exit words
                self.close_nicely()

        except KeyboardInterrupt:
            self._logger.info("Pressed Control + C from main")
            self.close_nicely()
    
    def communicate(self, text: str, channels: list):
        """
        Communicates to the user using the channels defined.

        It is an abstraction to deliver in one shot display and audio (and whatever else in the future).
        It is a NOT blocking process, runs every channel in a separate process so they can run in parallel,
        speeding up the overall run.
        
        Every Process needs to be managed a bit different:
        - TTS is an always running Process that listens to a Queue for new messages to say.
        - Display needs to be created per message to show, as we don't have a persistent process
        """

        # In case we want TTS, we need to pause the mic
        # this is done within the TTS process via a shared memory flag that tells the STT to pause

        if self.COMM_TTS in channels:
            # Say the answer
            self._logger.debug("Say Communication")
            # We already have the TTS in a Process, listening for elements in the queue
            self._say(text)

        if self.COMM_DISPLAY in channels:
            # Show the answer
            self._logger.debug("Show Communication")
            self._show(text)


        # Wait for the processes to end
        if self.COMM_TTS in channels:
            # We don't wait, just let it talk. We control the mic via shared_memeory flags
            pass
        if self.COMM_DISPLAY in channels:
            pass
    
    def _text_has_exit_intention(self, text):
        return text in self._exit_words
    
    def close_nicely(self):
        sw_closing = self._stopwatch.continue_or_start(name="closing")
        self._logger.debug("Closing nicely...")

        # Clean the displays
        self.clear_displays()

        # Wait for all the queues to get empty
        self.wait_for_all_queues_to_finish()

        # Finish all related multiprocess stuff
        self.finish_leftover_processes()

        # ------ Final logs ------

        self._logger.debug("We should be now nicely closed")
        self._logger.debug("⏱️  Closed: " + str(self._stopwatch.stop(sw_closing)))

        # Here comes anything that we want to do before leaving
        self._logger.info("⏱️  Final Stopwatch report:\n" + self._stopwatch.stop_and_report())
        self._logger.info("💡  Memory used:" + str(Memory.use(Memory.MEGABYTES)) + " MB")
    
    def clear_displays(self):
        self._logger.debug("Clearing the eInk.")
        self._clear_display()
        self._logger.debug("Clearing the LED Matrix.")
        self._clear_matrix()
    
    def wait_for_all_queues_to_finish(self):
        # Now wait until the displays finish being busy
        self._logger.debug("Waiting for all queues to get empty")
        self._logger.debug("Current queues size: \n" +
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

        self._logger.debug("All queues are empty now. I've sleept " + str(total_sleeping) + "s.")

    def finish_leftover_processes(self):
        # We can't join() child processes unless all queues get totally consumed.

        # 1. Send a "finish" to the children. Needs the queue.
        # TODO: I believe that the issue is due to not waiting for this 'finish' to be read by the children
        #    from the queues. Maybe the main thread empties it before being read. 
        self._logger.debug("[Main Finish] Send 'finish' to children")
        self._finish_subprocess()
        # ...so they can close dependencies.

        # 2. Clean and close the queues, apparently better from the one that put().
        self._logger.debug("[Main Finish] Empty and close queues")
        self.clearAndDiscardQueue(self._queue_display)
        self.clearAndDiscardQueue(self._queue_matrix)
        self.clearAndDiscardQueue(self._queue_speech)
        # At this point the queues should be closed.

        # 3. Joining the queues to the main thread.
        self._logger.debug("[Main Finish] Joining queues")
        self._queue_display.join()
        self._queue_matrix.join()
        self._queue_speech.join()

        # We don't need to ask the process to self-terminate. It will when it finishes the job.
        # self._queue.put((QueueItemType.ACTION,QueueItemAction.FINISH))
        self._logger.debug("[Main Finish] Is the Speech subprocess still alive? " + ("Yes" if self._speech.is_alive() else "No"))
        if self._speech.is_alive():
            self._logger.debug("[Main Finish] Terminating TTS Process")
            self._speech.terminate()
            # kill() does not fail (terminate() sometimes does), but appears to me pretty hardcode.
            # self._speech.kill()
        
        self._logger.debug("[Main Finish] Is the Display subprocess still alive? " + ("Yes" if self._display.is_alive() else "No"))
        if self._display.is_alive():
            self._logger.debug("[Main Finish] Terminating Display Process")
            self._display.terminate()
        
        self._logger.debug("[Main Finish] Is the Matrix subprocess still alive? " + ("Yes" if self._matrix.is_alive() else "No"))
        if self._matrix.is_alive():
            self._logger.debug("[Main Finish] Terminating Matrix Process")
            self._matrix.terminate()
        
        # Close the Shared Memory
        self._logger.debug("[Main Finish] Closing Shared Memory")
        self._shared_memory.shm.close()
        self._shared_memory.shm.unlink()
    

    # ------- Communication with Queues ---------

    def _init_subprocess(self, who: QueueItemType = QueueItemType.ACTION):

        if who == QueueItemType.ACTION:
            self._queue_speech.put((who, QueueItemAction.INITIALIZE))
            self._queue_display.put((who, QueueItemAction.INITIALIZE))
            self._queue_matrix.put((who, QueueItemAction.INITIALIZE))
        elif who == QueueItemType.DISPLAY:
            self._queue_display.put((who, QueueItemAction.INITIALIZE))
        elif who == QueueItemType.SPEECH:
            self._queue_speech.put((who, QueueItemAction.INITIALIZE))
        elif who == QueueItemType.MATRIX:
            self._queue_matrix.put((who, QueueItemAction.INITIALIZE))
        else:
            self._logger.error("I can't understand who should I initialise: " + who)

    
    def _finish_subprocess(self, who: QueueItemType = QueueItemType.ACTION):

        if who == QueueItemType.ACTION:
            self._queue_speech.put((who, QueueItemAction.FINISH))
            self._queue_display.put((who, QueueItemAction.FINISH))
            self._queue_matrix.put((who, QueueItemAction.FINISH))
        elif who == QueueItemType.DISPLAY:
            self._queue_display.put((who, QueueItemAction.FINISH))
        elif who == QueueItemType.SPEECH:
            self._queue_speech.put((who, QueueItemAction.FINISH))
        elif who == QueueItemType.MATRIX:
            self._queue_matrix.put((who, QueueItemAction.FINISH))
        else:
            self._logger.error("I can't understand who should I finish: " + who)
    
    def _say(self, message: str):
        self._queue_speech.put((QueueItemType.SAY, message))
    
    def _show(self, message: str):
        self._queue_display.put((QueueItemType.SHOW, message))
        self._queue_matrix.put((QueueItemType.SHOW, message))
    
    def _startup_splash(self):
        self._queue_display.put((QueueItemType.DISPLAY, QueueItemDisplay.STARTUP))
    
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