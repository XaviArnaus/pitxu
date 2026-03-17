from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager, SHARED_USER_IS_SPEAKING
from pitxu.lib.utils.signal_tools import SignalTools
from pitxu.lib.utils.xtime import Xtime
from pitxu.lib.utils.audio_graph import AudioGraph

from scipy import signal, io
import numpy as np
import numpy.fft as fft
from datetime import datetime
from rms_vad import RmsVAD, VADConfig, compute_energy_db
import os
import logging
from audiomath import Sound
import soundfile as sf


class Preprocessor(PyXavi):

    # Desired frequency range for human voice (e.g., telephone band)
    LOWCUT_FREQ = 300  # Hz
    # LOWCUT_FREQ = 100  # Hz
    HIGHCUT_FREQ = 3400 # Hz
    # HIGHCUT_FREQ = 1100 # Hz
    # FILTER_ORDER = 3   # Order of the filter (higher order means steeper rolloff)
    FILTER_ORDER = 5   # Order of the filter (higher order means steeper rolloff)

    RATE = 16000  # Sampling rate

    shared_memory: SharedMemoryManager = None
    vad: RmsVAD = None
    audio_graph: AudioGraph = None

    # energy_average: float = 0.0
    last_human_speaking_datetime: datetime = None

    # Weight for the new energy value in the moving average calculation (between 0 and 1)
    # A higher weight means that the average will react more quickly to changes in energy,
    # while a lower weight means that the average will be more stable and less affected by short-term fluctuations.
    NEW_ENERGY_WEIGHT = 0.1

    # # Define a threshold for what constitutes a "peak" in energy.
    # # This can be adjusted based on experimentation.
    # # 1st try: 1.5 times the average energy
    # # PEAK_THRESHOLD = 1.5    # -> Too low, it detects everything as human.
    # # 2nd try: 1.25 times the average energy
    # # PEAK_THRESHOLD = 1.25  # -> Too low, it detects everything as human.
    # # 3rd try: 1.75 times the average energy
    # # PEAK_THRESHOLD = 1.75  # -> Too low
    # # 4th try: 2.0 times the average energy
    # PEAK_THRESHOLD = 500.0  # 

    # # Define a threshold for what constitutes a "peak" in filtered energy.
    # PEAK_FILTERED_THRESHOLD = 1.0  # 
    
    ENERGY_RATIO_THRESHOLD = 0.9

    # How long to wait after the last detected human speaking before considering that the user has stopped speaking (in seconds)
    SPEAKING_SILENCE_TIMEOUT_SECONDS = 1

    # Control if we're currently in a "speaking" state, which can help to avoid false positives when the user is speaking continuously.
    user_is_speaking: bool = False

    accummulated_signal: list = []
    accummulated_filtered_signal: list = []
    # acc_signal: list = []

    signal_plots_path = os.path.join("audio", "signals")
    signal_plots_path_name = "audio_signals_%s.png"
    signal_plots_path_name_latest = "_latest.png"
    spectrograms_plots_path = os.path.join("audio", "spectrograms")
    spectrograms_plots_path_name = "audio_spectrograms_%s.png"
    spectrograms_plots_path_name_latest = "_latest.png"
    audio_files_location: str = None
    preprocessed_audio_files_location: str = None

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_AUDIO_PATH = "audio/"
    DEFAULT_AUDIO_INPUT_PATH = "input/"
    DEFAULT_PREPROCESSED_AUDIO_INPUT_PATH = "preprocessed_input/"
    FILENAME_PREFIX = "audio_"
    FILENAME_EXTENSION = ".wav"

    VERBOSE_DEBUG: bool = True
    DEBUG_ENERGY_FACTOR = 1

    def __init__(self, config: Config, params: Dictionary):
        super(Preprocessor, self).init_pyxavi(config=config, params=params)

        self._xlog.info("🎤 Initializing Preprocess for Speech-to-Text")

        if params.key_exists("samplerate"):
            self.RATE = params.get("samplerate")
        elif self._xconfig.get("speech-to-text.preprocessor.input_samplerate", None) is not None and \
             self._xconfig.get("speech-to-text.preprocessor.input_samplerate", None) > 0:
            self.RATE = self._xconfig.get("speech-to-text.preprocessor.input_samplerate")
        else:
            self._xlog.warning(f"No samplerate provided in params to Preprocess, using default of {self.RATE} Hz")

        self._prepare_dump_audio_files()
        
        # Initialize the VAD with the provided configuration
        threshold = self._xconfig.get("speech-to-text.vad.threshold", 0.6)
        attack = self._xconfig.get("speech-to-text.vad.attack", 0.2)
        release = self._xconfig.get("speech-to-text.vad.release", 1.5)
        self.vad = RmsVAD(VADConfig(threshold=threshold, attack=attack, release=release, sample_rate=self.RATE))
        
        self.LOWCUT_FREQ = self._xconfig.get("speech-to-text.preprocessor.lowcut_freq", self.LOWCUT_FREQ)
        self.HIGHCUT_FREQ = self._xconfig.get("speech-to-text.preprocessor.highcut_freq", self.HIGHCUT_FREQ)
        self.FILTER_ORDER = self._xconfig.get("speech-to-text.preprocessor.filter_order", self.FILTER_ORDER)
        # self.NEW_ENERGY_WEIGHT = self._xconfig.get("speech-to-text.preprocessor.new_energy_weight", self.NEW_ENERGY_WEIGHT)
        # self.PEAK_THRESHOLD = self._xconfig.get("speech-to-text.preprocessor.peak_energy_threshold_multiplier", self.PEAK_THRESHOLD)
        # self.PEAK_FILTERED_THRESHOLD = self._xconfig.get("speech-to-text.preprocessor.peak_filtered_energy_threshold_multiplier", self.PEAK_FILTERED_THRESHOLD)
        self.SPEAKING_SILENCE_TIMEOUT_SECONDS = self._xconfig.get("speech-to-text.preprocessor.silence_timeout_seconds", self.SPEAKING_SILENCE_TIMEOUT_SECONDS)

        self.log_summary("Preprocessor Initialization", [
            ("LOWCUT_FREQ", f"{self.LOWCUT_FREQ} Hz"),
            ("HIGHCUT_FREQ", f"{self.HIGHCUT_FREQ} Hz"),
            ("FILTER_ORDER", f"{self.FILTER_ORDER}"),
            ("RATE", f"{self.RATE} Hz"),
            # ("NEW_ENERGY_WEIGHT", f"{self.NEW_ENERGY_WEIGHT}"),
            # ("PEAK_THRESHOLD", f"{self.PEAK_THRESHOLD}x average energy"),
            # ("PEAK_FILTERED_THRESHOLD", f"{self.PEAK_FILTERED_THRESHOLD}x average filtered energy"),
            ("SPEAKING_SILENCE_TIMEOUT_SECONDS", f"{self.SPEAKING_SILENCE_TIMEOUT_SECONDS} seconds"),
            ("VAD Threshold", threshold),
            ("VAD Attack", f"{attack} seconds"),
            ("VAD Release", f"{release} seconds")
        ])

        # Pre-calculate settings
        # window_size_seconds = self.CHUNK / self.RATE
        # step_size_seconds = self.CHUNK / self.RATE
        # self.window_size_samples = int(window_size_seconds * self.RATE)
        # self.step_size_samples = int(step_size_seconds * self.RATE)

        self.shared_memory = SharedMemoryManager(config=config, params=params)
        self.shared_memory.initialize_existing_shared_memory_flags()

        self.audio_graph = AudioGraph(config=config, params=params)

        logging.getLogger("matplotlib").setLevel(self._xconfig.get("libs_logger.matplotlib.loglevel", logging.WARNING))

        self._log_debug("🎤 Done Initializing Preprocess for Speech-to-Text")
    
    def _prepare_dump_audio_files(self):

        self.signal_plots_path = os.path.join(self._xconfig.get("storage.path"), self.signal_plots_path)
        self.spectrograms_plots_path = os.path.join(self._xconfig.get("storage.path"), self.spectrograms_plots_path)

        self.preprocessed_audio_files_location = self._xconfig.get("storage.path", self.DEFAULT_STORAGE_PATH) + \
                                    self._xconfig.get("storage.audio.path", self.DEFAULT_AUDIO_PATH) + \
                                    self._xconfig.get("storage.audio.preprocessed_input", self.DEFAULT_PREPROCESSED_AUDIO_INPUT_PATH)
        self.audio_files_location = self._xconfig.get("storage.path", self.DEFAULT_STORAGE_PATH) + \
                                    self._xconfig.get("storage.audio.path", self.DEFAULT_AUDIO_PATH) + \
                                    self._xconfig.get("storage.audio.input", self.DEFAULT_AUDIO_INPUT_PATH)
        if os.path.exists(self.audio_files_location) == False:
            os.makedirs(self.audio_files_location)
        if os.path.exists(self.preprocessed_audio_files_location) == False:
            os.makedirs(self.preprocessed_audio_files_location)
    
    def preprocess_chunk(self, indata: bytes) -> bytes | None:
        # What we receive from the STT queue are raw (non-numpy) bytes in int16 dtype format.
        # What is needed for preprocessing and so on are numpy arrays
        # Ensure that what we return here are bytes in int16!
        self._xlog.debug(f"🎤 Preprocess: Received audio chunk of {len(indata)} bytes for preprocessing.")

        # All calculations are done with numpy arrays for performance reasons, so convert it first.
        # We work here internally with INT16 (PCM_16) format.
        audio_data_np = self.byte_chunk_to_numpy_array(indata)
        # audio_data_np = SignalTools.float32(self.byte_chunk_to_numpy_array(indata))

        # Apply bandpass filter to isolate human voice frequencies
        filtered_audio_np = self.bandpass_filter(audio_data_np, normalize_filtered_outcome=True)
        # The following works, but I feel that it is a FFT-based filter is more expensive and less effective than the Butterworth one, which is designed for this purpose.
        # filtered_audio_np = self.fftBandpass(audio_data_np, self.LOWCUT_FREQ, self.HIGHCUT_FREQ, fs=self.RATE)

        # Maintain the accummulators
        self.add_to_accumulated_signal_np(audio_data_np, filtered_audio_np)
        # self.acc_signal.append(indata)

        return indata

        # All calculations are done with numpy arrays for performance reasons, so convert it first.
        audio_data_np = self.byte_chunk_to_numpy_array(indata)

        # Apply bandpass filter to isolate human voice frequencies
        filtered_audio_np = self.bandpass_filter(audio_data_np)
        filtered_audio_in_bytes = self.numpy_array_to_byte_chunk(filtered_audio_np)

        # Get the energy ratio in human frequencies over the energy in all frequencies.
        audio_energy_ratio = self.get_energy_ratio(audio_data_np)

        # Is this chunk the first in a segment?
        if self.accummulated_signal.size == 0:
            self._log_debug(f"🎤 🟢 VAD detected speech in the chunk.")

        self.log_summary(f"Chunk Analysis for {len(indata)} bytes", [
            # ("Audio type", f"{type(indata)}, {audio_data_np.dtype}"),
            # ("Filtered Audio type", f"{type(filtered_audio_np)}, {filtered_audio_np.dtype}"),
            ("Filtered Audio Length", f"{len(filtered_audio_in_bytes)} bytes"), 
            ("Filtered Audio Energy VAD", f"{compute_energy_db(filtered_audio_np):.2f} dB"),
            ("Filtered Audio Enery Ratio", f"{audio_energy_ratio:.4f}"),
            # ("Is VAD Speech?", f"{self.is_vad_speech(filtered_audio_in_bytes)}"),
            (f"Energy Ratio >= Threshold ({self.ENERGY_RATIO_THRESHOLD})?", f"{audio_energy_ratio >= self.ENERGY_RATIO_THRESHOLD}"),
            # ("Is user speaking?", f"{self.is_user_speaking()}")
            ("Acc. signal length", f"{len(self.accummulated_signal.tobytes())} bytes"),
            ("Acc. Filtered signal length", f"{len(self.accummulated_filtered_signal.tobytes())} bytes"),
        ])

        self.accummulated_signal = np.concatenate((self.accummulated_signal, audio_data_np))
        self.accummulated_filtered_signal = np.concatenate((self.accummulated_filtered_signal, filtered_audio_np))

        # If the VAD detects speech in the filtered chunk, we move on.
        if audio_energy_ratio >= self.ENERGY_RATIO_THRESHOLD:
        # if self.is_vad_speech(filtered_audio_in_bytes) and \
        #     audio_energy_ratio >= self.ENERGY_RATIO_THRESHOLD:
            self._log_debug(f"🎤 🟢 VAD detected speech in the chunk.")

            # We have a filtered audio that is likely to be a human speaking, why should we just add the original?
            return bytes(filtered_audio_in_bytes)
    
        
        # VAD did not recognise this chunk as speech
        else:
            # If we were speaking, give some time to allow human pauses.
            self._log_debug(f"🗣️ 🟠 NOT human speaking detected, still in the human speaking window by VAD.")

            # Check if we should unset the "user is speaking" state based on the silence timeout
            # This is useless, as it's the VAD in the callback that decides the last pause length.
            # if self.is_beyond_silence_threshold():
                # self.plot_signals()
                # self.accummulated_signal = np.array([], dtype=np.int16)
                # self.accummulated_filtered_signal = np.array([], dtype=np.int16)
                # self._log_debug(f"🗣️ 📈 Plotted at: {self.signal_plots_path_latest}")

            # Keep adding this audio chunk to the queue.
            # self.queue.put(bytes(indata))
            # self.queue.put(filtered_audio_np.tobytes())
            return bytes(filtered_audio_in_bytes)

        # else:
        #     # self._log_debug(f"🗣️ 🔴 NOT human speaking.")
        #     return None
    
    def on_speech_end(self):
        # This is meant to be called from the VAD callback when it detects the end of speech, to reset the state and allow new detections.

        if len(self.accummulated_signal) == 0:
            return

        input_signal = np.concatenate(self.accummulated_signal)
        filtered_signal = np.concatenate(self.accummulated_filtered_signal)

        # max_input = np.max(np.abs(input_signal))
        # if max_input > 0:
        #     # input_signal = (input_signal / max_input).astype(np.float32) if max_input > 0 else input_signal.astype(np.float32)
        #     input_signal = (input_signal / max_input).astype(np.float32)

        # max_filtered = np.max(np.abs(filtered_signal))
        # if max_filtered > 0:
        #     # filtered_signal = (filtered_signal / max_filtered).astype(np.float32) if max_filtered > 0 else filtered_signal.astype(np.float32)
        #     filtered_signal = (filtered_signal / max_filtered).astype(np.float32)

        # max_input = np.max(np.abs(input_signal))
        # input_signal = (input_signal / max_input).astype(np.int16) if max_input > 0 else input_signal.astype(np.int16)

        # max_filtered = np.max(np.abs(filtered_signal))
        # filtered_signal = (filtered_signal / max_filtered).astype(np.int16) if max_filtered > 0 else filtered_signal.astype(np.int16)

        # clean_input = b""
        # for chunk in self.acc_signal:
        #     clean_input += chunk

        self.plot_signals(input_signal, filtered_signal)
        self.plot_spectograms(input_signal, filtered_signal)
        # self._save_audio_bytes(
        #     clean_input,
        #     os.path.join(self.audio_files_location, f"__{self.FILENAME_PREFIX}{Xtime.now_key()}{self.FILENAME_EXTENSION}"), 
        #     os.path.join(self.audio_files_location, f"__latest{self.FILENAME_EXTENSION}"))
        self.save_input_audio(input_signal)
        self.save_preprocessed_audio(filtered_signal)
        self.accummulated_signal = []
        self.accummulated_filtered_signal = []
        # self.acc_signal = []
        self._log_debug(f"🗣️ 🔴 End speaking.")

    def is_vad_speech(self, chunk: bytes) -> bool:
        # This is a simple wrapper around the VAD to check if the chunk contains speech.
        # It can be used as an additional check before doing more expensive calculations like energy analysis.

        events = self.vad.feed(chunk)
        dd(events)
        is_speech = self.vad.is_speaking
        self.vad.reset()
        return is_speech
    
    def add_to_accumulated_signal(self, signal_chunk: bytes, filtered_signal_chunk: bytes):
        signal_chunk_np = self.byte_chunk_to_numpy_array(signal_chunk)
        filtered_signal_chunk_np = self.byte_chunk_to_numpy_array(filtered_signal_chunk)
        self.add_to_accumulated_signal_np(signal_chunk_np, filtered_signal_chunk_np)
    
    def add_to_accumulated_signal_np(self, signal_chunk: np.ndarray, filtered_signal_chunk: np.ndarray):
        # self.accummulated_signal = np.concatenate((self.accummulated_signal, signal_chunk), dtype=np.int16)
        # self.accummulated_filtered_signal = np.concatenate((self.accummulated_filtered_signal, filtered_signal_chunk), dtype=np.int16)
        self.accummulated_signal.append(signal_chunk)
        self.accummulated_filtered_signal.append(filtered_signal_chunk)
    
    def plot_signals(self, input_signal: np.ndarray = None, filtered_signal: np.ndarray = None):

        if self._xconfig.get("speech-to-text.generate_signal_plots", False):
            audio_graph = AudioGraph(config=self._xconfig, params=self._xparams)
            audio_graph.plot_waveform_comparison(
                input_signal,
                filtered_signal, 
                self.RATE, 
                filepath=self.signal_plots_path,
                filename=self.signal_plots_path_name % Xtime.now_key(),
                also_latest=True,
                main_title="Original vs Filtered Audio Signal",
                signal_name_1=f"Original signal {self.RATE} Hz",
                signal_name_2=f"Butterworth bandpass {self.LOWCUT_FREQ}-{self.HIGHCUT_FREQ} Hz")

            self._log_debug(f"🗣️ 📈 Plotted audio segment at: {os.path.join(self.signal_plots_path, self.signal_plots_path_name_latest)}")
    
    def plot_spectograms(self, input_signal: np.ndarray = None, filtered_signal: np.ndarray = None):

        if self._xconfig.get("speech-to-text.generate_spectrogram_plots", False):
            audio_graph = AudioGraph(config=self._xconfig, params=self._xparams)
            audio_graph.plot_spectrogram_comparison(
                input_signal,
                filtered_signal, 
                self.RATE, 
                filepath=self.spectrograms_plots_path,
                filename=self.spectrograms_plots_path_name % Xtime.now_key(),
                also_latest=True,
                main_title="Input Audio Spectrogram",
                signal_name_1=f"Original signal {self.RATE} Hz",
                signal_name_2=f"Butterworth bandpass {self.LOWCUT_FREQ}-{self.HIGHCUT_FREQ} Hz")

            self._log_debug(f"🗣️ 📈 Plotted audio spectrogram segment at: {os.path.join(self.spectrograms_plots_path, self.spectrograms_plots_path_name_latest)}")
    
    def save_preprocessed_audio(self, audio_data_np: np.ndarray):
        # Save the preprocessed audio data to a file for debugging purposes
        if self._xconfig.get("speech-to-text.preprocessor.save_preprocessed_audio", False):
            filename = os.path.join(self.preprocessed_audio_files_location, f"{self.FILENAME_PREFIX}{Xtime.now_key()}{self.FILENAME_EXTENSION}")
            filename_latest = os.path.join(self.preprocessed_audio_files_location, f"_latest{self.FILENAME_EXTENSION}")
            self._save_audio(audio_data_np, filename, filename_latest)
    
    def save_input_audio(self, audio_data_np: np.ndarray):
        # Save the input audio data to a file for debugging purposes
        if self._xconfig.get("speech-to-text.save_input_audio", False):
            filename = os.path.join(self.audio_files_location, f"{self.FILENAME_PREFIX}{Xtime.now_key()}{self.FILENAME_EXTENSION}")
            filename_latest = os.path.join(self.audio_files_location, f"_latest{self.FILENAME_EXTENSION}")
            self._save_audio(audio_data_np, filename, filename_latest)
    
    def _save_audio(self, audio_data_np: np.ndarray, filename: str, filename_latest: str):
        # sf.write(file=filename, samplerate=self.RATE, data=audio_data_np, format="WAV", subtype="PCM_16")
        io.wavfile.write(filename, self.RATE, audio_data_np)
        if os.path.exists(filename_latest):
            os.remove(filename_latest)
        # sf.write(file=filename_latest, samplerate=self.RATE, data=audio_data_np, format="WAV", subtype="PCM_16")
        audio_data_np.nbytes
        io.wavfile.write(filename_latest, self.RATE, audio_data_np)
        self._xlog.debug(f"💾 Dumped audio [{audio_data_np.nbytes} bytes] of [{audio_data_np.dtype}] to file: {filename}")
    
    # def _save_audio_bytes(self, audio_data: bytes, filename: str, filename_latest: str):
    #     # sf.write(file=filename, samplerate=self.RATE, data=np.frombuffer(audio_data, dtype=np.int16), format="WAV", subtype="PCM_16")
    #     io.wavfile.write(filename, self.RATE, np.frombuffer(audio_data, dtype=np.int16))
    #     if os.path.exists(filename_latest):
    #         os.remove(filename_latest)
    #     # sf.write(file=filename_latest, samplerate=self.RATE, data=np.frombuffer(audio_data, dtype=np.int16), format="WAV", subtype="PCM_16")
    #     io.wavfile.write(filename_latest, self.RATE, np.frombuffer(audio_data, dtype=np.int16))
    #     self._xlog.debug(f"💾 Dumped audio [{len(audio_data)} bytes] to file: {filename}")

    
    
    # --- Helpers ---
    
    def byte_chunk_to_numpy_array(self, byte_chunk: bytes) -> np.ndarray:
        """
        Convert a byte chunk of audio data to a NumPy array.

        Parameters:
        byte_chunk (bytes): The input byte chunk of audio data.

        Returns:
        np.ndarray: The converted NumPy array of audio samples.
        """
        # Convert the byte chunk to a NumPy array of int16
        audio_array = np.frombuffer(byte_chunk, dtype=np.int16)
        return audio_array
    
    def numpy_array_to_byte_chunk(self, audio_array: np.ndarray) -> bytes:
        """
        Convert a NumPy array of audio samples back to a byte chunk.

        Parameters:
        audio_array (np.ndarray): The input NumPy array of audio samples.

        Returns:
        bytes: The converted byte chunk of audio data.
        """
        # Ensure the audio array is in int16 format before converting to bytes
        if audio_array.dtype != np.int16:
            audio_array = audio_array.astype(np.int16)
        byte_chunk = audio_array.tobytes()
        return byte_chunk
    
    # --- Signal calculations ---
    
    def bandpass_filter(self, audio_data_np: np.ndarray, normalize_filtered_outcome: bool = True) -> np.ndarray:
        """
        Apply a Butterworth bandpass filter to the input audio data.

        Parameters:
        audio_data_np (np.ndarray): The input audio data.

        Returns:
        np.ndarray: The filtered audio data.
        """

        # Human speech primarily occupies a specific range of frequencies. While the full audible spectrum is 20 Hz to 20,000 Hz,
        #   most of the critical information for speech intelligibility lies within a narrower band,
        #   often considered to be around 300 Hz to 3400 Hz (the "telephone band"). Background noise, hums, 
        #   or other unwanted sounds often exist outside this range (e.g., low-frequency rumble, high-frequency hiss).

        # By applying a **band-pass filter**, we can effectively "filter" an audio recording to retain only
        #   the frequencies within the human voice range and attenuate (reduce the amplitude of) frequencies outside this range. 
        #   This helps to clean up recording by removing extraneous noise, making the voice clearer.

        # If the data comes in stereo, transform it to mono
        if audio_data_np.ndim > 1:
            audio_data_np = np.mean(audio_data_np, axis=1)

        # Convert to float for filtering (important for signal processing)
        audio_data_np = SignalTools.float32(audio_data_np)
        # audio_data_np = audio_data_np.astype(np.float32)

        # Design the Butterworth bandpass filter
        nyquist = 0.5 * self.RATE
        low = self.LOWCUT_FREQ / nyquist
        high = self.HIGHCUT_FREQ / nyquist
        wp = np.array([self.LOWCUT_FREQ, self.HIGHCUT_FREQ])*2/self.RATE  # normalized pass band frequnecies
        ws = np.array([0.8*self.LOWCUT_FREQ, 1.2*self.HIGHCUT_FREQ])*2/self.RATE  # normalized stop band frequencies
        # b, a = signal.butter(self.FILTER_ORDER, [low, high], btype='band')
        # sos = signal.butter(self.FILTER_ORDER, [low, high], btype='band', output='sos', fs=self.RATE)
        # sos = signal.butter(self.FILTER_ORDER, [low, high], btype='band', analog=True, output='sos')
        # sos = signal.butter(self.FILTER_ORDER, [low, high], btype='band', analog=False, output='sos', fs=self.RATE)
        sos = signal.iirdesign(wp, ws, gpass=60, gstop=80, ftype="butter", analog=False, output="sos")

        # Apply the filter to the audio data.
        # Attention, it returns float64
        # filtered_audio_np = signal.lfilter(b, a, audio_data_np)
        # filtered_audio_np = signal.sosfiltfilt(sos, audio_data_np, padlen=len(audio_data_np) - 1)
        zi = signal.sosfilt_zi(sos)
        filtered_audio_np, zf = signal.sosfilt(sos, audio_data_np, zi=zi*audio_data_np[0])
        # filtered_audio_np = signal.sosfilt(sos, audio_data_np)

        # Normalize the filtered audio to prevent clipping and ensure it stays within the int16 range
        if normalize_filtered_outcome:
            max_val = np.max(np.abs(filtered_audio_np))
            if max_val > 0:
                filtered_audio_np = filtered_audio_np / max_val

        # Convert back this audio so the further operations find the common ground
        # filtered_audio_np = (filtered_audio_np * (2**15 - 1)).clip(-32768, 32767)
        filtered_audio_np = SignalTools.int16(filtered_audio_np)
        # filtered_audio_np = filtered_audio_np.astype(np.int16)

        return filtered_audio_np
    
    def fftBandpass(self, x, low, high, fs=1.0):
        """
        Apply a bandpass signal via FFTs.

        Parameters
        ----------
        x : array_like
            Input signal vector. Assumed to be real-only.
        low : float
            Lower bound of the passband in Hertz. (If less than or equal
            to zero, a high-pass filter is applied.)
        high : float
            Upper bound of the passband, Hertz.
        fs : float
            Sample rate in units of samples per second. If `high > fs / 2`,
            the output is low-pass filtered.

        Returns
        -------
        y : ndarray
            Output signal vector with all frequencies outside the `[low, high]`
            passband zeroed.

        Caveat
        ------
        Note that the energe in `y` will be lower than the energy in `x`, i.e.,
        `sum(abs(y)) < sum(abs(x))`. 
        """
        xf = fft.rfft(x)
        f = fft.rfftfreq(len(x), d=1 / fs)
        xf[f < low] = 0
        xf[f > high] = 0
        return fft.irfft(xf, len(x))
    
    def get_energy_ratio(self, audio_buffer: np.ndarray) -> float:
        """
        Calculate the ratio of energy in the human voice frequency range to the total energy of the audio signal.

        Parameters:
        audio_buffer (np.ndarray): The input audio data.

        Returns:
        float: The ratio of energy in the human voice frequency range to the total energy.
        """
        # This approach uses Discrete Fourier Transform to calculate the energy of the signal across different frequencies.
        # This means that we have energy per frequency.
        energy_per_frequencies = SignalTools.energy(audio_buffer, self.RATE)

        # Sum speech energy
        speechenergy = 0
        for f, e in energy_per_frequencies.items():
            if self.LOWCUT_FREQ <= f <= self.HIGHCUT_FREQ:
                speechenergy += e

        # Calculate ratio of speech energy to total energy and return
        ratio = speechenergy / sum(energy_per_frequencies.values())
        return ratio
    
    def is_user_speaking(self) -> bool:
        """
        Checks if the user is currently speaking.
        Only Local based.
        """
        return self.shared_memory.read_shared_memory_flag(SHARED_USER_IS_SPEAKING)
    
    def is_beyond_silence_threshold(self, silence_timeout_seconds: int = SPEAKING_SILENCE_TIMEOUT_SECONDS) -> bool:
        '''
        Checks if the user should be considered as not speaking anymore, based on the last time we detected human speaking and a silence timeout.
        This can be used to automatically unset the "user is speaking" state after a certain period of silence, which can help to keep the state accurate without requiring explicit signals for when the user stops speaking.
        '''
        if self.last_human_speaking_datetime is not None:
            time_since_last_speaking = (datetime.now() - self.last_human_speaking_datetime).total_seconds()
            if time_since_last_speaking > silence_timeout_seconds:
                return True
        return False

    # def preprocess_chunk(self, indata: bytes) -> bytes | None:
    #     # What we receive from the STT queue are raw (non-numpy) bytes in int16 dtype format.
    #     # What is needed for preprocessing and so on are numpy arrays
    #     # Ensure that what we return here are bytes in int16!

    #     # All calculations are done with numpy arrays for performance reasons, so convert it first.
    #     audio_data = self.byte_chunk_to_numpy_array(indata)

    #     # Apply bandpass filter to isolate human voice frequencies
    #     filtered_audio = self.bandpass_filter(audio_data)

    #     # Calculate the energy of the filtered audio (to ensure it's a human speaking)
    #     filtered_energy = self.get_energy(filtered_audio, filter_out_unwanted_freqs=True)

    #     # Get the voice energy ration compared with all energy in the chunk
    #     filtered_energy_ratio = self.get_energy_ratio(audio_data)

    #     self.log_summary(f"Energy Analysis for chunk of {len(indata)} bytes", [
    #         # ("Audio type", f"{type(indata)}, {audio_data.dtype}"),
    #         ("Energy Average", f"{self.energy_average * self.DEBUG_ENERGY_FACTOR:.2f}"),
    #         # ("Filtered Audio type", f"{type(filtered_audio)}, {filtered_audio.dtype}"),
    #         # ("Filtered Audio Length", f"{len(filtered_audio)} bytes"), 
    #         ("Filtered Audio Energy", f"{filtered_energy * self.DEBUG_ENERGY_FACTOR:.2f} (x{filtered_energy / self.energy_average:.2f})"),
    #         ("Filtered Audio Enery Ratio", f"{filtered_energy_ratio:.4f}")
    #     ])

    #     # # Sometimes we get an energy calculation that is extremely high for the scale we're working.
    #     # # I don't understand why, so we just dump it in the logs but we simple skip it to avoid messing up with calculations,
    #     # # and also to avoid impacting the speaking timeout.
    #     # if filtered_energy > self.energy_average * 1000:
    #     #     self._xlog.warning(f"❗️ Detected an unusually high energy value of {filtered_energy:.2f} (x{filtered_energy / self.energy_average:.2f} compared to average). Skipping this chunk.")
    #     #     return None

    #     # Check if the energy of the filtered audio is a peak compared to the average energy
    #     # if self.filtered_energy_is_a_peak(filtered_energy):
    #     if filtered_energy_ratio > 0.60:
    #         self._log_debug(f"🗣️ 🟢 Detected human speaking. ")

    #         # Identify that the user is speaking, to control it here and in the rest of the app.
    #         self.set_user_is_speaking()

    #         # We have a filtered audio that is likely to be a human speaking, why should we just add the original?
    #         # self.queue.put(bytes(indata))
    #         # self.queue.put(filtered_audio.tobytes())
    #         return bytes(self.numpy_array_to_byte_chunk(filtered_audio))
    #     else:
    #         if self.is_user_speaking():
    #             # As we have a feedback loop after transcription, we don't add this energy to the average yet.

    #             self._log_debug(f"🗣️ 🟠 NOT human speaking detected, still in the human speaking window.")

    #             # Check if we should unset the "user is speaking" state based on the silence timeout
    #             if self.should_unset_user_is_speaking():
    #                 # self._xlog.debug(f"🗣️ Unsetting user is speaking state due to silence timeout.")
    #                 self.unset_user_is_speaking()

    #             # Keep adding this audio chunk to the queue.
    #             # self.queue.put(bytes(indata))
    #             # self.queue.put(filtered_audio.tobytes())
    #             return bytes(self.numpy_array_to_byte_chunk(filtered_audio))

    #         else:
    #             self._log_debug(f"🗣️ 🔴 NOT human speaking.")

    #             # self._xlog.debug(f"🗣️ It was not a human voice and the user is not currently speaking. Adding it into the energy average but not putting it in the processing queue.")
    #             self.add_energy_to_average(filtered_energy)
        
    #     return None
    
    # def preprocess_chunk_double_energy(self, indata: bytes) -> bytes | None:
    #     # What we receive from the STT queue are raw (non-numpy) bytes in int16 dtype format.
    #     # What is needed for preprocessing and so on are numpy arrays
    #     # Ensure that what we return here are bytes in int16!

    #     # All calculations are done with numpy arrays for performance reasons, so convert it first.
    #     audio_data = self.byte_chunk_to_numpy_array(indata)

    #     # Calculate the energy of the audio block
    #     energy = self.get_energy(audio_data, filter_out_unwanted_freqs=True)

    #     # If the energy is a peak compared to the average energy, continue processing the audio block and don't add this read to the energy average.
    #     if self.energy_is_a_peak(energy):
    #         # self._xlog.debug(f"🗣️ Energy: Peak: {energy * self.DEBUG_ENERGY_FACTOR:.2f} (x{energy / self.energy_average:.2f}), Average: {self.energy_average * self.DEBUG_ENERGY_FACTOR:.2f}")

    #         # Apply bandpass filter to isolate human voice frequencies
    #         filtered_audio = self.bandpass_filter(audio_data)

    #         # Calculate the energy of the filtered audio (to ensure it's a human speaking)
    #         filtered_energy = self.get_energy(filtered_audio, filter_out_unwanted_freqs=True)

    #         self.log_summary(f"Energy Analysis for chunk of {len(indata)} bytes", [
    #             ("Audio type", f"{type(indata)}, {audio_data.dtype}"),
    #             ("Energy Peak", f"{energy * self.DEBUG_ENERGY_FACTOR:.2f} (x{energy / self.energy_average:.2f})"),
    #             ("Energy Average", f"{self.energy_average * self.DEBUG_ENERGY_FACTOR:.2f}"),
    #             ("Filtered Audio type", f"{type(filtered_audio)}, {filtered_audio.dtype}"),
    #             ("Filtered Audio Length", f"{len(filtered_audio)} bytes"),
    #             ("Filtered Audio Energy", f"{filtered_energy * self.DEBUG_ENERGY_FACTOR:.2f} (x{filtered_energy / self.energy_average:.2f})")
    #         ])

    #         # Sometimes we get an energy calculation that is extremely high for the scale we're working.
    #         # I don't understand why, so we just dump it in the logs but we simple skip it to avoid messing up with calculations,
    #         # and also to avoid impacting the speaking timeout.
    #         if filtered_energy > self.energy_average * 1000:
    #             self._xlog.warning(f"❗️ Detected an unusually high energy value of {filtered_energy:.2f} (x{filtered_energy / self.energy_average:.2f} compared to average). Skipping this chunk.")
    #             return None

    #         # Check if the energy of the filtered audio is a peak compared to the average energy
    #         if self.filtered_energy_is_a_peak(filtered_energy):
    #             self._log_debug(f"🗣️ 🟢 Detected human speaking. ")

    #             # Identify that the user is speaking, to control it here and in the rest of the app.
    #             self.set_user_is_speaking()

    #             # We have a filtered audio that is likely to be a human speaking, why should we just add the original?
    #             # self.queue.put(bytes(indata))
    #             # self.queue.put(filtered_audio.tobytes())
    #             return bytes(self.numpy_array_to_byte_chunk(filtered_audio))
    #         else:
    #             if self.is_user_speaking():
    #                 # As we have a feedback loop after transcription, we don't add this energy to the average yet.

    #                 self._log_debug(f"🗣️ 🟠 NOT human speaking detected, still in the human speaking window.")

    #                 # Check if we should unset the "user is speaking" state based on the silence timeout
    #                 if self.should_unset_user_is_speaking():
    #                     # self._xlog.debug(f"🗣️ Unsetting user is speaking state due to silence timeout.")
    #                     self.unset_user_is_speaking()

    #                 # Keep adding this audio chunk to the queue.
    #                 # self.queue.put(bytes(indata))
    #                 # self.queue.put(filtered_audio.tobytes())
    #                 return bytes(self.numpy_array_to_byte_chunk(filtered_audio))

    #             else:
    #                 self._log_debug(f"🗣️ 🔴 NOT human speaking.")

    #                 # self._xlog.debug(f"🗣️ It was not a human voice and the user is not currently speaking. Adding it into the energy average but not putting it in the processing queue.")
    #                 self.add_energy_to_average(energy)

    #     # If it's not, then just update the average energy and skip processing the audio block.
    #     else:
    #         if self.is_user_speaking():
    #             # As we have a feedback loop after transcription, we don't add this energy to the average yet.

    #             self._log_debug(f"🗣️ 🟠 NOT a peak, still in the human speaking window.")

    #             # Check if we should unset the "user is speaking" state based on the silence timeout
    #             if self.should_unset_user_is_speaking():
    #                 # self._xlog.debug(f"🗣️ Unsetting user is speaking state due to silence timeout.")
    #                 self.unset_user_is_speaking()

    #             # Keep adding this audio chunk to the queue.
    #             return bytes(indata)
    #         else:
    #             # self._xlog.debug(f"🗣️ It was not a human voice and the user is not currently speaking. Adding it into the energy average but not putting it in the processing queue.")
    #             self.add_energy_to_average(energy)
        
    #     return None

    # def get_energy(self, audio_buffer: np.ndarray, filter_out_unwanted_freqs = False) -> float:
    #     """
    #     Calculate the energy of the audio signal.

    #     Parameters:
    #     audio_data (np.ndarray): The input audio data.

    #     Returns:
    #     float: The energy of the audio signal.
    #     """
    #     # audio_buffer = audio_buffer.astype(float) / 32768.0 # Normalize to -1 to 1

    #     # # features, feature_names = ShortTermFeatures.feature_extraction(audio_buffer, self.RATE,
    #     # #                                                                    self.window_size_samples,
    #     # #                                                                    self.step_size_samples,
    #     # #                                                                    deltas=True)
    #     # # current_energy = features[1, 0] # Energy is typically at index 1
    #     # current_energy = np.sum(audio_buffer ** 2) / np.float64(len(audio_buffer))
    #     # return current_energy

    #     # This approach uses Discrete Fourier Transform to calculate the energy of the signal across different frequencies.
    #     # This means that we have energy per frequency.
    #     energy_per_frequencies = SignalTools.energy(audio_buffer, self.RATE)

    #     # # Sum speech energy
    #     # speechenergy = 0
    #     # for f, e in energy_per_frequencies.items():
    #     #     if self.LOWCUT_FREQ <= f <= self.HIGHCUT_FREQ:
    #     #         speechenergy += e

    #     # In case that we want the energy only from the range of frequencies that are relevant for us.
    #     if filter_out_unwanted_freqs:
    #         energy_per_frequencies = dict(filter(lambda fe: self.LOWCUT_FREQ <= fe[0] <= self.HIGHCUT_FREQ, energy_per_frequencies.items()))

    #     # AVG speech energy
    #     speechenergy = statistics.fmean(energy_per_frequencies.values())

    #     # SUM speech energy
    #     speechenergy = sum(energy_per_frequencies.values())
        
    #     # Calculate ratio of speech energy to total energy and return
    #     # ratio = speechenergy / sum(energy_per_frequencies.values())
    #     # logger.debug("SPEECH %.4f", ratio)
    #     # return ratio >= self.vadthreshold
        
    #     # return ratio
    #     return speechenergy

    # def normalize_volume(self, audio_data: np.ndarray, target_dBFS: float = -20.0) -> np.ndarray:
    #     """
    #     Normalize the volume of the audio data to a target level.

    #     Parameters:
    #     audio_data (np.ndarray): The input audio data.
    #     target_dBFS (float): The target volume level in dBFS.
    #     Returns:
    #     np.ndarray: The volume-normalized audio data.
    #     """
    #     # Normalize the volume of the audio data to a target level (e.g., -20 dBFS)
    #     current_dBFS = 20 * np.log10(np.max(np.abs(audio_data)) + 1e-6)  # Avoid log(0)
    #     gain = 10 ** ((target_dBFS - current_dBFS) / 20)
    #     normalized_audio = audio_data * gain
    #     return normalized_audio
    
    # ---- Energy control ---

    # def add_energy_to_average(self, energy: float):
    #     '''
    #     Adds the energy of an audio block to the average energy using a simple moving average.
    #     This can be used to keep track of the average energy of the audio input, which can help to detect peaks in energy that may indicate speech activity.
    #     '''
    #     weight_for_current_average = 1 - self.NEW_ENERGY_WEIGHT
    #     self.energy_average = weight_for_current_average * self.energy_average + self.NEW_ENERGY_WEIGHT * energy
    
    # def energy_is_a_peak(self, energy: float) -> bool:
    #     '''
    #     Checks if the energy of the audio block is a peak compared to the average energy, which can be an indication of speech activity.
    #     This can be used to trigger certain actions only when there is a significant increase in energy, which may indicate that the user has started speaking.
    #     '''
    #     if self.energy_average == 0:
    #         return False  # Avoid division by zero

    #     return energy > self.PEAK_THRESHOLD * self.energy_average

    # def filtered_energy_is_a_peak(self, energy: float) -> bool:
    #     '''
    #     Checks if the filtered energy of the audio block is a peak compared to the average energy, which can be an indication of speech activity.
    #     This can be used to trigger certain actions only when there is a significant increase in energy, which may indicate that the user has started speaking.
    #     '''
    #     if self.energy_average == 0:
    #         return False  # Avoid division by zero

    #     return energy > self.PEAK_FILTERED_THRESHOLD * self.energy_average
    
    # def add_untranscripted_audio_energy_to_average(self, audio_data: bytes):
    #     '''
    #     Adds the energy of an audio block that was not transcribed (e.g., because it was not detected as speech) to the average energy.
    #     This can help to keep the average energy updated for chunks identified as human voice but lead to no transcription.
    #     '''
    #     energy = self.get_energy(self.byte_chunk_to_numpy_array(audio_data), filter_out_unwanted_freqs=True)
    #     self._xlog.debug(f"🗣️ Adding energy ({energy:.2f}) of untranscripted audio chunk to average {self.energy_average:.2f} to keep it updated.")
    #     self.add_energy_to_average(energy)

    # ---- States ----
    
    # def set_user_is_speaking(self):
    #     """
    #     Sets the state to indicate that the user is currently speaking.
    #     Local flag, Shared memory flag, and ALWAYS resets the last human speaking datetime to now.
    #     """
    #     if not self.user_is_speaking:
    #         self.user_is_speaking = True
    #         self.shared_memory.write_shared_memory_flag(SHARED_USER_IS_SPEAKING, True)

    #     # Keep it updated anyways
    #     self.last_human_speaking_datetime = datetime.now()
    
    # def unset_user_is_speaking(self):
    #     """
    #     Unsets the state to indicate that the user is no longer speaking.
    #     Local flag, Shared memory flag, and ALWAYS nullifies the last human speaking datetime.
    #     """
    #     if self.user_is_speaking:
    #         self.user_is_speaking = False
    #         self.shared_memory.write_shared_memory_flag(SHARED_USER_IS_SPEAKING, False)

    #     # Ensure it is reset.
    #     self.last_human_speaking_datetime = None