from pyxavi import Config, Dictionary

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction
from pitxu.lib.microservice.client import Client
import sounddevice
import logging
import time

class TextToSpeech(Xprocess):

    _client: Client = None
    _output_stream: sounddevice.OutputStream = None

    DEFAULT_SAMPLERATE: int = 22050

    def get_process_name(self) -> str:
        return "TTS"
    
    def initialize(self):
        self._client = Client(config=self._xconfig, params=self._xparams)
        self._client.initialize()

        self._log_debug("Creating Piper Output Stream with samplerate: " + str(self.DEFAULT_SAMPLERATE))
        self._output_stream = sounddevice.OutputStream(
            samplerate=self.DEFAULT_SAMPLERATE,
            blocksize=0,
            channels=1,
            dtype='int16'
        )
    
    def finish(self):
        self._xlog.debug("Closing output stream")
        if self._output_stream is not None:
            self._output_stream.close()
        self._xlog.debug("Done finishing TTS Worker")
    
    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        
        if action == XprocAction.SAY and param != "":
            self.say(param)
    
    def say(self, text: str):

        if self._xconfig.get("text-to-speech.mock", True):
            self._xlog.warning("Mocking TTS by Config. Should have said [" + text + "]")
            # Emulate that we're doing something by waiting a second per 10 words
            words = text.split(" ")
            wait_time = max(1, len(words) / 10)
            self._xlog.debug(f"Mocking TTS wait time for {wait_time} seconds")
            time.sleep(wait_time)

        else:
            self._xlog.debug("Saying [" + text.replace("\n", "\\n") + "]")

            # Get the audio bytes for the given text
            self._log_debug("Getting audio data from the server")
            audio_data = self._client.synthesize(text=text)
            audio_bytes = audio_data.get("audio_bytes", b"")
            sample_rate = audio_data.get("sample_rate", self.DEFAULT_SAMPLERATE)
            
            self._output_stream.start()

            self._log_debug("Writing audio bytes to output stream")
            self._output_stream.write(audio_bytes)

            self._log_debug("All audio chunks processed, stopping output stream")
            self._output_stream.stop()
        
        self._log_debug("Finished saying communication")

        
    
