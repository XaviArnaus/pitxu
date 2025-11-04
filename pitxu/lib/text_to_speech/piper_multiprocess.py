from multiprocessing import Process, Queue, shared_memory
import numpy as np
import sounddevice
from piper.voice import PiperVoice

from pyxavi import Logger, Config, Dictionary

import logging

from pitxu.lib.dto import QueueItemType, QueueItemAction
from pitxu.lib.utils import ConfigLoader
from definitions import ROOT_DIR

# Trying here to make a Worker for Multiprocessing.
class PiperMultiprocess(Process):

    MODELS_PATH = "tts_models/"

    _config: Config = None
    _logger: logging = None
    _parameters: Dictionary = None

    _queue: Queue = None
    _shared_memory: shared_memory.ShareableList = None

    _model: None
    _voice: None
    _output_stream: sounddevice.OutputStream = None

    def __init__(self, config: Config, params: Dictionary, queue: Queue):
        '''
        Initialisation of the class, this is called from main.
        After the start(), all triggers come from the queue, being constantly checked by run()
        '''
        self._parameters = params
        self._config = config
        self._logger = Logger(config=config, base_path=self._parameters.get("base_path", "")).get_logger()
        # Need all previous to start logging :-)
        self._logger.debug("Instantiating Piper TTS")

        self._queue = queue

        super(PiperMultiprocess, self).__init__()
    
    def initialize(self):
        self._logger.info("Initializing Piper TTS")
        language = self._parameters.get("language")
        model_name = self._config.get("text-to-speech.per_language." + language)
        self._model = ROOT_DIR + "/" + self._config.get("storage.path") + self.MODELS_PATH + model_name + ".onnx"
        self._voice = PiperVoice.load(self._model)
        self._output_stream = sounddevice.OutputStream(
            # samplerate=self._voice.config.sample_rate,
            samplerate=self._get_samplerate(),
            blocksize=0,
            device=self._config.get("text-to-speech.output_device", None),
            channels=1,
            dtype='int16',
        )

        self._logger.info("Loading flags from Shared Memory")
        self._shared_memory = shared_memory.ShareableList(name=self._parameters.get("shared_memory_name"))
        if self._shared_memory is None:
            self._logger.error("Shared Memory is None, cannot read 'pause_mic' flag")

        self._logger.debug("Done Initializing Piper TTS")
    
    def run(self):
        '''
        Managed by Process
        Gets called whenever the self._queue.put() is called from the main.py
        '''

        # Apparently the parent Process class has a run() implementation,
        # but I don't see the difference in behaviour.
        super(PiperMultiprocess, self).run()

        try:
            # This is needed to have the logging connected:
            # - Create the Config object from scratch
            # - Use the Config object to initialise the Logger. Be sure that the `stdout.multiprocess`
            #       or `file.multiprocess` is True. Each activate their respective multiproces support.
            #       WARNING: Unintentionally, stdout works multiprocess without activating! Bug!
            # - ONLY THEN we will see logging messages in the main logger.
            self._config = ConfigLoader.load_config_files()
            self._logger = Logger(config=self._config, base_path=self._parameters.get("base_path", "")).get_logger()


            self._logger.debug("Piper Worker runs")
            for queue_item in iter(self._queue.get, None):
                type, message = queue_item
                self._logger.debug("Piper Worker received a [" + type + "]: [" + message + "]")

                # Says the message received
                if type == QueueItemType.MESSAGE and message != "":
                    self.say(message)
                
                # Initializes the model from within the Process.
                # This is the only way to avoid Model Session issues
                if type == QueueItemType.ACTION and message == QueueItemAction.INITIALIZE:
                    self.initialize()

                # We don't need to finish the subprocess from main explicitly, it will end when the job
                #   is done or when we call join() from main.
                # Still, we leave it so we have the tool for whatever other reason.
                if type == QueueItemType.ACTION and message == QueueItemAction.FINISH:
                    self.finish()

        except KeyboardInterrupt:
            self._logger.debug("Pressed Control + C while running Speech subprocess")
            self.finish()
                
    
    def say(self, text: str):

        self.pause_mic()

        if self._config.get("text-to-speech.mock", True):
            self._logger.warning("Mocking TTS by Config. Should have said [" + text + "]")
        else:
            self._logger.debug("Saying [" + text.replace("\n", "\\n") + "]")
            self._output_stream.start()

            for audio_bytes in self._voice.synthesize_stream_raw(text):
                int_data = np.frombuffer(audio_bytes, dtype=np.int16)
                self._output_stream.write(int_data)

            self._output_stream.stop()
        
        self.resume_mic()
    
    def finish(self):
        '''
        This is called from from run() via KeyboardInterrupt or from outside via Queue
        to finish gracefully whatever we have open.
        Do not try to terminate the process from inside itself.
        '''
        self._logger.debug("Closing output stream")
        self._output_stream.close()
        self._logger.debug("Done finishing Piper Worker")
    
    def pause_mic(self):
        self._shared_memory[0] = True

    def resume_mic(self):
        self._shared_memory[0] = False

    def _get_samplerate(self) -> int:
        device_info = sounddevice.query_devices(self._config.get("text-to-speech.output_device", None), "output")
        # soundfile expects an int, sounddevice provides a float:
        return int(device_info["default_samplerate"])