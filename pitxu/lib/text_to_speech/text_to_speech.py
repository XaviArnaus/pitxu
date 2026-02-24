from pyxavi import Config, Dictionary

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction
from pitxu.lib.microservice.client import Client
import sounddevice
import logging
import time

from definitions import SHARED_CHATBOT_BUSY, SHARED_SPEAKER_BUSY

class TextToSpeech(Xprocess):

    _client: Client = None
    _output_stream: sounddevice.OutputStream = None
    _last_gathered_audio: bytes = None

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
        
        if action == XprocAction.GATHER_TTS and param != "":
            self.get_audio_from_text(param)
        
        if action == XprocAction.PLAY_TTS:
            self.write_audio_to_output_stream()

    
    def get_audio_from_text(self, text: str):

        if self._xconfig.get("text-to-speech.mock", True):
            self._xlog.warning("Mocking TTS by Config. Should have said [" + text + "]")
            # Emulate that we're doing something by waiting a second per 10 words
            words = text.split(" ")
            wait_time = max(1, len(words) / 10)
            self._xlog.debug(f"Mocking TTS wait time for {wait_time} seconds")
            time.sleep(wait_time)

            self._last_gathered_audio = b"MOCK_AUDIO_BYTES_FOR_" + text.encode("utf-8")
        else:
            self._log_debug("Getting audio data from the server")

            self.set_chatbot_busy()

            audio_data = self._client.synthesize(text=text)
            audio_bytes = audio_data.get("audio_bytes", b"")
            sample_rate = audio_data.get("sample_rate", self.DEFAULT_SAMPLERATE)

            self._last_gathered_audio = audio_bytes

            self.unset_chatbot_busy()
    
    def write_audio_to_output_stream(self):

        if self._xconfig.get("text-to-speech.mock", True):
            self._xlog.warning("Mocking TTS by Config. It would be playing [" + str(len(self._last_gathered_audio)) + "] bytes of audio.")
            # Emulate that we're doing something by waiting 3 seconds
            time.sleep(3)
        else:
            self.set_speaking_busy()

            self._log_debug("Writing audio bytes to output stream")
            self._output_stream.start()
            self._output_stream.write(self._last_gathered_audio)
            self._log_debug("All audio chunks processed, stopping output stream")
            self._output_stream.stop()

            self.unset_speaking_busy()
    
    # Overloading the busy methods to set a flag that the chatbot is busy, so that the UI can show some feedback to the user.
    # We'll controll the flags from here.
    
    def set_busy(self):
        pass

    def unset_busy(self):
        pass

    def set_speaking_busy(self):
        self.write_shared_memory_flag(SHARED_SPEAKER_BUSY, True)
        self._log_debug("🔈 Setting Speaker as busy.")
    
    def unset_speaking_busy(self):
        self.write_shared_memory_flag(SHARED_SPEAKER_BUSY, False)
        self._log_debug("🔈 Unsetting Speaker as busy.")
    
    def set_chatbot_busy(self):
        self.write_shared_memory_flag(SHARED_CHATBOT_BUSY, True)
        self._log_debug("🔈 Setting Chatbot as busy.")
    
    def unset_chatbot_busy(self):
        self.write_shared_memory_flag(SHARED_CHATBOT_BUSY, False)
        self._log_debug("🔈 Unsetting Chatbot as busy.")

        
    
