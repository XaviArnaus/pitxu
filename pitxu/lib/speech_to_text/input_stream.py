from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

import sounddevice
import threading

class InputStream(PyXavi):
    """
    This class is responsible for managing the audio input stream. 
    It captures audio from the microphone, processes it, and feeds it into the speech-to-text pipeline.
    There was a previous approach where this was done inside a separate Thread, but the Sounddevice library already 
        handles the audio capture in a separate thread, so we don't need to manage threading ourselves.
    """

    input_stream: sounddevice.RawInputStream = None

    samplerate: int = None
    blocksize: int = None
    device: str = None
    capture_handler_callback: callable = None

    _lock: threading.Lock = None

    def __init__(self, config: Config, params: Dictionary):
        super(InputStream, self).init_pyxavi(config, params)

        self.initialize()
    
    def initialize(self):
        self._xlog.debug("Initializing InputStream...")

        # We need the audio parameters.
        if self._xparams.key_exists("audio_parameters"):
            self._audio_parameters = self._xparams.get("audio_parameters")
        else:
            self._xlog.error("Audio parameters not found in configuration. Please ensure that 'audio_parameters' is defined in the configuration.")
            raise ValueError("Audio parameters not found in configuration.")
        
        # We need also the capture callback handler
        if self._xparams.key_exists("capture_handler_callback"):
            self.capture_handler_callback = self._xparams.get("capture_handler_callback")
        else:
            self._xlog.error("Capture handler not found in configuration. Please ensure that 'capture_handler_callback' is defined in the configuration.")
            raise ValueError("Capture handler not found in configuration.")
        
        self.samplerate = self._audio_parameters.get("input_samplerate")
        self.blocksize = self._xconfig.get("speech-to-text.blocksize", 1024)
        self.device = self._xparams.get("audio_parameters.input_device", None)

        self.log_summary("Input Stream (Mic) initialized", [
                    ("Device", self.device if self.device is not None else "None (Default)"),
                    ("Sample Rate", self.samplerate if self.samplerate is not None else "None"),
                    ("Block Size", self.blocksize if self.blocksize > 0 else "0 (automatic by pyAudio)"),
                    ("Channels", 1),
                    ("Data Type", "int16"),
                    ("Callback", "CaptureHandler.callback")
                ])

        # Create the lock for thread safety
        self._lock = threading.Lock()
        
        self.input_stream = sounddevice.RawInputStream(
                #samplerate=self._dictate.samplerate,
                # samplerate=16000, # Vosk works better with 16kHz, even if the mic supports higher rates.
                samplerate=self.samplerate,
                # blocksize=0, 
                blocksize=self.blocksize,
                device=self.device,
                dtype="int16", 
                channels=1,
                # callback=self._dictate.callback) as input_stream:
                callback=self.capture_handler_callback)
        
        self._xlog.debug("InputStream initialized successfully.")

    def start(self):
        with self._lock:
            if not self.input_stream.active:
                self.input_stream.start()
                self._log_debug("InputStream started.")

    def stop(self):
        with self._lock:
            if self.input_stream.active:
                self.input_stream.stop()
                self._log_debug("InputStream stopped.")

    def close(self):
        with self._lock:
            self.input_stream.close()
            self._log_debug("InputStream closed.")

    
class MockedInputStream(InputStream):
    """
    This is a mocked version of the InputStream, which can be used for testing purposes. 
    It simulates the behavior of the actual input stream without capturing real audio data. 
    This allows us to test the speech-to-text pipeline and other components without relying on a microphone or audio input.
    """

    def initialize(self):
        self._xlog.debug("Initializing MockedInputStream... (no actual audio capture will occur)")
        self._xlog.debug("MockedInputStream initialized successfully.")

    def start(self):
        self._xlog.info("Starting MockedInputStream... (no actual stream to start)")

    def stop(self):
        self._xlog.info("Stopping MockedInputStream... (no actual stream to stop)")
    
    def close(self):
        self._xlog.info("Closing MockedInputStream... (no actual stream to close)")