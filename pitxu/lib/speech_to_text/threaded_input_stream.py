from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

import sounddevice
import threading

class ThreadedInputStream(PyXavi):
    """
    This class is responsible for managing the audio input stream in a separate thread. 
    It captures audio from the microphone, processes it, and feeds it into the speech-to-text pipeline. 
    By running the audio capture in a separate thread, we can ensure that the main application remains responsive 
        and can handle other tasks concurrently.
    """

    input_stream: sounddevice.RawInputStream = None

    samplerate: int = None
    blocksize: int = None
    device: str = None
    capture_handler_callback: callable = None
    finished_callback: callable = None

    recording_thread: threading.Thread = None

    THREAD_NAME = "InputStream"

    def __init__(self, config: Config, params: Dictionary):
        super(ThreadedInputStream, self).init_pyxavi(config, params)

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
        
        # We need also the finished callback handler
        if self._xparams.key_exists("finished_callback"):
            self.finished_callback = self._xparams.get("finished_callback")
        else:
            self._xlog.error("Finished callback not found in configuration. Please ensure that 'finished_callback' is defined in the configuration.")
            raise ValueError("Finished callback not found in configuration.")
        
        self.samplerate = self._audio_parameters.get("input_samplerate")
        self.blocksize = self._xconfig.get("speech-to-text.blocksize", 1024)
        self.device = self._xparams.get("audio_parameters.input_device", None)

        self.log_summary("Threaded Raw Input Stream (Mic) initialized", [
                    ("Device", self.device if self.device is not None else "None (Default)"),
                    ("Sample Rate", self.samplerate if self.samplerate is not None else "None"),
                    ("Block Size", self.blocksize if self.blocksize > 0 else "0 (automatic by pyAudio)"),
                    ("Channels", 1),
                    ("Data Type", "int16"),
                    ("Callback", "CaptureHandler.callback")
                ])
        
        # Now we start the thread.
        self.recording_thread = threading.Thread(target=self._input_stream_worker, name=self.THREAD_NAME, daemon=True)
        self.start_recording()
        
        self._xlog.debug("InputStream initialized successfully.")
    
    def start_recording(self):
        if self.recording_thread is not None:
            self._xlog.debug("Starting the input stream...")
            self.recording_thread.start()
            self._xlog.debug("Input stream started.")
        else:
            self._xlog.error("Input stream is not initialized. Cannot start recording.")
    
    def close(self):
        self._xlog.info("Closing InputStream...")

        if self.input_stream is not None:
            self.input_stream.close()
            self._xlog.debug("Input stream closed successfully.")
        else:
            self._xlog.debug("Input stream was not open, no need to close.")
        
        self.recording_thread.join(timeout=2)
        if self.recording_thread.is_alive():
            self._xlog.warning("Input stream thread did not terminate within the timeout period.")
        else:
            self._xlog.debug("Input stream thread terminated successfully.")
        
        self._log_debug("InputStream closed.")
    
    def get_input_stream(self):
        return self.input_stream
    
    def _input_stream_worker(self):
        """
        This method runs in a separate thread and is responsible for capturing audio from the microphone. 
        It continuously reads audio data and feeds it into the speech-to-text pipeline for processing.
        """
        self._xlog.debug("Input stream worker started.")

        # This is the samplerate that generates the chunks received in CaptureHandler.callback().
        #   In MacOS the microphone can't be set to an arbitrary samplerate that fits on us, so
        #   the config value for it must be -1 so that it gets inferred by de library.
        # Then the CaptureHeader will resample it to 16 kHz, and that's why the rest of components work
        #   under 16 kHz.
        # Set the samplerate that we're going to settle for the STT (ensure that the STT model has the EXACT SAME VALUE)
        # Fall back to what the Vosk's Kaldi Recognizer is using if the config value is not set.
        samplerate = self._audio_parameters.get("input_samplerate")
        blocksize = self._xconfig.get("speech-to-text.blocksize", 1024)
        device = self._xparams.get("audio_parameters.input_device", None)

        self._xlog.debug("Initialising the Raw Input Stream for microphone")
        self.input_stream = sounddevice.RawInputStream(
                            #samplerate=self._dictate.samplerate,
                            # samplerate=16000, # Vosk works better with 16kHz, even if the mic supports higher rates.
                            samplerate=samplerate,
                            # blocksize=0, 
                            blocksize=blocksize,
                            device=device,
                            dtype="int16", 
                            channels=1,
                            # callback=self._dictate.callback) as input_stream:
                            callback=self.capture_handler_callback)
    
class MockedInputStream(ThreadedInputStream):
    """
    This is a mocked version of the ThreadedInputStream, which can be used for testing purposes. 
    It simulates the behavior of the actual input stream without capturing real audio data. 
    This allows us to test the speech-to-text pipeline and other components without relying on a microphone or audio input.
    """

    def initialize(self):
        self._xlog.debug("Initializing MockedInputStream... (no actual audio capture will occur)")
        self._xlog.debug("MockedInputStream initialized successfully.")
    
    def close(self):
        self._xlog.info("Closing MockedInputStream... (no actual stream to close)")
    
    def get_input_stream(self):
        return None  # No actual stream, since this is a mock.