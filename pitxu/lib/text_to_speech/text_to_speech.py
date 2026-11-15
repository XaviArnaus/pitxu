from pyxavi import Config, Dictionary

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction
from pitxu.lib.microservice.client import Client
import sounddevice
import logging
import time

from definitions import SHARED_CHATBOT_BUSY, SHARED_SPEAKER_BUSY, SHARED_NETWORK_BUSY, SHARED_SPEECH_INTERRUPT_REQUESTED

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

            self.set_communication_busy()

            audio_data = self._client.synthesize(text=text)
            audio_bytes = audio_data.get("audio_bytes", b"")
            sample_rate = audio_data.get("sample_rate", self.DEFAULT_SAMPLERATE)

            self._last_gathered_audio = audio_bytes

            self.unset_communication_busy()
    
    def write_audio_to_output_stream(self):

        # An old request (a press that came too late for the previous speech) must never cut this one.
        self.write_shared_memory_flag(SHARED_SPEECH_INTERRUPT_REQUESTED, False)

        if self._xconfig.get("text-to-speech.mock", True):
            self._xlog.warning("Mocking TTS by Config. It would be playing [" + str(len(self._last_gathered_audio)) + "] bytes of audio.")
            # Emulate that we're doing something by waiting 3 seconds, in slices so it can be interrupted.
            for _ in range(30):
                if self._is_speech_interrupt_requested():
                    self._xlog.info("🤐 Speech interrupted (mocked).")
                    break
                time.sleep(0.1)
        else:
            self.set_speaking_busy()

            self._log_debug("Writing audio bytes to output stream")
            self._output_stream.start()

            # The same bytes, in order, in slices: the blocking write keeps pacing the playback,
            # and we get the chance to look at the interruption between slices.
            # 16 bit samples: 2 bytes per frame. 0 slice seconds writes everything at once.
            slice_bytes = int(self.DEFAULT_SAMPLERATE * float(self._xconfig.get("text-to-speech.interrupt_slice_seconds", 0.1))) * 2
            step = slice_bytes if slice_bytes > 0 else len(self._last_gathered_audio)
            interrupted = False
            for start in range(0, len(self._last_gathered_audio), max(step, 1)):
                if self._is_speech_interrupt_requested():
                    interrupted = True
                    break
                self._output_stream.write(self._last_gathered_audio[start:start + step])

            if interrupted:
                self._xlog.info("🤐 Speech interrupted by the user.")
                # abort() drops what is already in the sound card buffer, stop() would play it out.
                self._output_stream.abort()
            else:
                self._log_debug("All audio chunks processed, stopping output stream")
                self._output_stream.stop()

            self.unset_speaking_busy()

        # Done, interrupted or not: the request is consumed.
        self.write_shared_memory_flag(SHARED_SPEECH_INTERRUPT_REQUESTED, False)

    def _is_speech_interrupt_requested(self) -> bool:
        try:
            return bool(self.read_shared_memory_flag(SHARED_SPEECH_INTERRUPT_REQUESTED))
        except Exception as e:
            self._log_debug(f"Could not read the speech interrupt flag: {e}")
            return False
    
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
    
    def set_communication_busy(self):
        self.write_shared_memory_flag(SHARED_NETWORK_BUSY, True)
        self._log_debug("🔈 Setting Communication as busy.")
    
    def unset_communication_busy(self):
        self.write_shared_memory_flag(SHARED_NETWORK_BUSY, False)
        self._log_debug("🔈 Unsetting Communication as busy.")

        
    
