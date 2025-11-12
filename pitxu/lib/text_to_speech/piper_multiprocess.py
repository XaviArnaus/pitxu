from multiprocessing import Process, JoinableQueue, shared_memory
import numpy as np
import sounddevice
from piper.voice import PiperVoice

from pyxavi import Logger, Config, Dictionary

import logging

from pitxu.lib.dto import QueueItemType, QueueItemAction
from pitxu.lib.utils import ConfigLoader
from definitions import ROOT_DIR, SHARED_SPEAKER_BUSY

# Trying here to make a Worker for Multiprocessing.
class PiperMultiprocess(Process):

    MODELS_PATH = "tts_models/"

    _xconfig: Config = None
    _xlog: logging = None
    _xparams: Dictionary = None

    _queue: JoinableQueue = None
    _shared_memory: shared_memory.ShareableList = None

    _model = None
    _voice: PiperVoice = None
    _output_stream: sounddevice.OutputStream = None

    def __init__(self, config: Config, params: Dictionary, queue: JoinableQueue):
        '''
        Initialisation of the class, this is called from main.
        After the start(), all triggers come from the queue, being constantly checked by run()
        '''
        self._xparams = params
        self._xconfig = config
        self._xlog = Logger(config=config, base_path=self._xparams.get("base_path", "")).get_logger()
        # Need all previous to start logging :-)
        self._xlog.debug("Instantiating Piper TTS")

        self._queue = queue

        super(PiperMultiprocess, self).__init__()
    
    def initialize(self):
        self._xlog.info("Initializing Piper TTS")
        language = self._xparams.get("language")
        model_name = self._xconfig.get("text-to-speech.per_language." + language)
        self._model = ROOT_DIR + "/" + self._xconfig.get("storage.path") + self.MODELS_PATH + model_name + ".onnx"
        self._voice = PiperVoice.load(self._model)
        self._output_stream = sounddevice.OutputStream(
            samplerate=self._voice.config.sample_rate,
            blocksize=0,
            channels=1,
            dtype='int16',
        )

        self._xlog.info("Loading flags from Shared Memory")
        self._shared_memory = shared_memory.ShareableList(name=self._xparams.get("shared_memory_name"))
        if self._shared_memory is None:
            self._xlog.error("Shared Memory is None, cannot read 'SHARED_SPEAKER_BUSY' flag")

        self._xlog.debug("Done Initializing Piper TTS")
    
    def finish(self):
        '''
        This is called from from run() via KeyboardInterrupt or from outside via Queue,
        to finish gracefully whatever we have open.
        Do not try to terminate the process from inside itself.
        '''
        self._xlog.debug("Closing output stream")
        self._output_stream.close()
        self._xlog.debug("Done finishing Piper Worker")
    
    def run(self):
        '''
        Managed by Process
        Gets called whenever the self._queue.put() is called from the main.py
        '''

        try:
            # Apparently the parent Process class has a run() implementation,
            # but I don't see the difference in behaviour.
            super(PiperMultiprocess, self).run()

            # This is needed to have the logging connected:
            # - Create the Config object from scratch
            # - Use the Config object to initialise the Logger. Be sure that the `stdout.multiprocess`
            #       or `file.multiprocess` is True. Each activate their respective multiproces support.
            #       WARNING: Unintentionally, stdout works multiprocess without activating! Bug!
            # - ONLY THEN we will see logging messages in the main logger.
            self._xconfig = ConfigLoader.load_config_files()
            self._xlog = Logger(config=self._xconfig, base_path=self._xparams.get("base_path", "")).get_logger()

            self._xlog.debug("Piper Worker runs")
            for queue_item in iter(self._queue.get, None):
                type, message = queue_item
                self._xlog.debug("Piper Worker received a [" + type + "]: [" + message + "]")

                # Says the message received
                if type == QueueItemType.SAY and message != "":
                    self.say(message)
                
                # Initializes the model from within the Process.
                # This is the only way to avoid Model Session issues
                if (type == QueueItemType.ACTION or type == QueueItemType.SPEECH) and message == QueueItemAction.INITIALIZE:
                    self.initialize()

                # We don't need to finish the subprocess from main explicitly, it will end when the job
                #   is done or when we call join() from main.
                # Still, we leave it so we have the tool for whatever other reason.
                if (type == QueueItemType.ACTION or type == QueueItemType.SPEECH) and message == QueueItemAction.FINISH:
                    self.finish()
            
            # Finally, we mark this task as done
            self._queue.task_done()

        except KeyboardInterrupt:
            self._xlog.debug("Pressed Control + C while running Speech subprocess")
            self.finish()
                
    
    def say(self, text: str):

        self.pause_mic()

        if self._xconfig.get("text-to-speech.mock", True):
            self._xlog.warning("Mocking TTS by Config. Should have said [" + text + "]")
        else:
            self._xlog.debug("Saying [" + text.replace("\n", "\\n") + "]")
            self._output_stream.start()

            for chunk in self._voice.synthesize(text):
                int_data = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
                self._output_stream.write(int_data)

            self._output_stream.stop()
        
        self.resume_mic()
    
    def pause_mic(self):
        self._shared_memory[SHARED_SPEAKER_BUSY] = True

    def resume_mic(self):
        self._shared_memory[SHARED_SPEAKER_BUSY] = False