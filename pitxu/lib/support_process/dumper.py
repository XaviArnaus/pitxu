from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.utils.xtime import Xtime
from pitxu.lib.utils.audio_graph import AudioGraph
from pitxu.lib.utils.conversors import Conversors

from scipy import io
import numpy as np
import os
from contextlib import contextmanager


class Dumper(PyXavi):

    audio_graph: AudioGraph = None

    samplerate: int = 16000
    lowcut_freq: int = 300
    highcut_freq: int = 3400

    accumulated_signal: list = []
    accumulated_filtered_signal: list = []

    unified_timestamp_str: str = None
    unified_timestamp_key: str = None

    signal_plots_path = os.path.join("audio", "signals")
    signal_plots_path_name = "audio_signal_%s.png"
    signal_plots_path_name_latest = "_latest.png"
    spectrograms_plots_path = os.path.join("audio", "spectrograms")
    spectrograms_plots_path_name = "audio_spectrogram_%s.png"
    spectrograms_plots_path_name_latest = "_latest.png"
    fourier_transform_plots_path = os.path.join("audio", "fourier_transforms")
    fourier_transform_plots_path_name = "audio_fourier_transform_%s.png"
    fourier_transform_plots_path_name_latest = "_latest.png"
    audio_files_location: str = None
    preprocessed_audio_files_location: str = None

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_AUDIO_PATH = "audio/"
    DEFAULT_AUDIO_INPUT_PATH = "input/"
    DEFAULT_PREPROCESSED_AUDIO_INPUT_PATH = "preprocessed_input/"
    FILENAME_PREFIX = "audio_"
    FILENAME_EXTENSION = ".wav"

    def __init__(self, config: Config, params: Dictionary):
        super(Dumper, self).init_pyxavi(config=config, params=params)

        self._xlog.info("🎤 Initializing Audio Dumper for Speech-to-Text")

        # Which samplerate do we use here?
        # The resampling happens in the CaptureHandler, and the accumulation of audio chunks happens in the next step, the Preprocessor.
        # So the samplerate of the "raw" audio data that we receive here is the `resample_target_samplerate` in the AudioParametersLoader.
        self.input_samplerate = params.get("audio_parameters.resample_target_samplerate", self.samplerate)
        self.preprocessing_samplerate = params.get("audio_parameters.preprocessing_samplerate", self.samplerate)
        self.lowcut_freq = params.get("audio_parameters.filter_lowcut_freq", self.lowcut_freq)
        self.highcut_freq = params.get("audio_parameters.filter_highcut_freq", self.highcut_freq)

        self._prepare_dump_audio_files()
        self._prepare_dump_plot_files()

        self.log_summary("Dumper Initialization", [
            ("Input Samplerate", f"{self.input_samplerate} Hz"),
            ("Preprocessing Samplerate", f"{self.preprocessing_samplerate} Hz"),
            ("Low cut frequency for plots", f"{self.lowcut_freq} Hz"),
            ("High cut frequency for plots", f"{self.highcut_freq} Hz"),
            ("Signal plots enabled", str(self._xconfig.get("speech-to-text.generate_signal_plots", False))),
            ("Spectrogram plots enabled", str(self._xconfig.get("speech-to-text.generate_spectrogram_plots", False))),
            ("Fourier transform plots enabled", str(self._xconfig.get("speech-to-text.generate_fourier_transform_plots", False))),
            ("Audio dump enabled", str(self._xconfig.get("speech-to-text.save_input_audio", False))),
            ("Preprocessed audio dump enabled", str(self._xconfig.get("speech-to-text.preprocessor.save_preprocessed_audio", False))),
            ("Signal plots path", self.signal_plots_path),
            ("Spectrogram plots path", self.spectrograms_plots_path),
            ("Fourier transform plots path", self.fourier_transform_plots_path),
            ("Audio files location", self.audio_files_location),
            ("Preprocessed audio files location", self.preprocessed_audio_files_location)
        ])
        
        self._log_debug("🎤 Done Initializing Audio Dumper for Speech-to-Text")
    
    # ----- Context managers for unified timestamps --------
    @contextmanager
    def unified_timestamp(self, timestamp_str: str = None, timestamp_key: str = None):
        """
        Context manager to use a unified timestamp for all dumped files within the context.
        This can be useful to correlate different dumped files (audio, plots, etc.) with the same timestamp in their filename, for easier correlation and debugging.
        The `timestamp_str` argument can be used to provide a custom timestamp string, otherwise the current time will be used.
        The `timestamp_key` argument can be used to provide a custom key for the timestamp, otherwise a default key will be used.
        """
        if timestamp_str is not None:
            self.unified_timestamp_str = timestamp_str
        else:
            self.unified_timestamp_str = Xtime.current_time_str()
        
        if timestamp_key is not None:
            self.unified_timestamp_key = timestamp_key
        else:
            self.unified_timestamp_key = Xtime.now_key()
        
        self._log_debug(f"Using unified timestamp: {self.unified_timestamp_str} with key: {self.unified_timestamp_key}")
        
        try:
            yield
        finally:
            self.unified_timestamp_str = None
            self.unified_timestamp_key = None
            self._log_debug("Cleared unified timestamp")
    
    # ------ Initialisation of the dumpers and folders for dumping the files --------
    
    def _prepare_dump_audio_files(self):

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
    
    def _prepare_dump_plot_files(self):

        self.signal_plots_path = os.path.join(self._xconfig.get("storage.path"), 
                                              self._xconfig.get("storage.signal_plots.path", self.signal_plots_path))
        self.spectrograms_plots_path = os.path.join(self._xconfig.get("storage.path"), 
                                                    self._xconfig.get("storage.spectrogram_plots.path", self.spectrograms_plots_path))
        self.fourier_transform_plots_path = os.path.join(self._xconfig.get("storage.path"), 
                                                         self._xconfig.get("storage.fourier_transform_plots.path", self.fourier_transform_plots_path))

        if self._xconfig.get("speech-to-text.generate_signal_plots", False):
            if os.path.exists(self.signal_plots_path) == False:
                os.makedirs(self.signal_plots_path)
        
        if self._xconfig.get("speech-to-text.generate_spectrogram_plots", False):
            if os.path.exists(self.spectrograms_plots_path) == False:
                os.makedirs(self.spectrograms_plots_path)
        
        if self._xconfig.get("speech-to-text.generate_fourier_transform_plots", False):
            if os.path.exists(self.fourier_transform_plots_path) == False:
                os.makedirs(self.fourier_transform_plots_path)
    
    # ------ Entry points for Xprocess calls --------
    
    def accumulate_audio(self, audio_data_np: np.ndarray, preprocessed: bool = False):
        # This is meant to be used when we want to accumulate audio data in memory, for example to dump it later in a single file.
        # The `preprocessed` flag is meant to differentiate between raw audio data and preprocessed audio data, which can be useful for debugging purposes.
        if preprocessed:
            self.accumulated_filtered_signal.append(audio_data_np)
            self._log_debug(f"Accumulated preprocessed audio data in memory: {len(self.accumulated_filtered_signal)} chunks")
        else:
            self.accumulated_signal.append(audio_data_np)
            self._log_debug(f"Accumulated raw audio data in memory: {len(self.accumulated_signal)} chunks")
    
    def clear_accumulated_audios(self):
        self.accumulated_signal = []
        self.accumulated_filtered_signal = []
        self._log_debug("Cleared accumulated audio data in memory")
    
    def dump_accumulated_audio(self, preprocessed: bool = False):
        # This is meant to be used when we want to dump the accumulated audio data in memory to a file, for example for debugging purposes.
        # The `preprocessed` flag is meant to differentiate between raw audio data and preprocessed audio data, which can be useful for debugging purposes.
        self._log_debug(f"Dumping accumulated {'preprocessed' if preprocessed else 'raw'} {len(self.accumulated_filtered_signal) if preprocessed else len(self.accumulated_signal)} audio chunks in memory to file.")
        if preprocessed:
            if len(self.accumulated_filtered_signal) > 0:
                self._log_debug(f"Dumping accumulated preprocessed audio data of {len(self.accumulated_filtered_signal)} chunks in memory to file")
                self.save_preprocessed_audio(audio_data_np=np.concatenate(self.accumulated_filtered_signal))
            else:
                self._log_debug("No preprocessed audio data in memory to dump")
        else:
            if len(self.accumulated_signal) > 0:
                self._log_debug(f"Dumping accumulated raw audio data of {len(self.accumulated_signal)} chunks in memory to file")
                self.save_input_audio(audio_data_np=np.concatenate(self.accumulated_signal))
            else:
                self._log_debug("No raw audio data in memory to dump")
    
    def plot_accumulated_audio(self):
        # This is meant to be used when we want to plot the accumulated audio data in memory, for example for debugging purposes.
        # The `preprocessed` flag is meant to differentiate between raw audio data and preprocessed audio data, which can be useful for debugging purposes.

        preprocessor_enabled = self._xconfig.get("speech-to-text.preprocessor.enabled", False)
        self._log_debug(f"Plotting accumulated audio data")

        if self._xconfig.get("speech-to-text.generate_signal_plots", False):
            self.plot_signals(input_signal=np.concatenate(self.accumulated_signal),
                              filtered_signal=np.concatenate(self.accumulated_filtered_signal if preprocessor_enabled else self.accumulated_signal))
        else:
            self._log_debug("Signal plots are disabled by configuration, skipping plotting of accumulated audio data")

        if self._xconfig.get("speech-to-text.generate_spectrogram_plots", False):
            self.plot_spectograms(input_signal=np.concatenate(self.accumulated_signal),
                                  filtered_signal=np.concatenate(self.accumulated_filtered_signal if preprocessor_enabled else self.accumulated_signal))
        else:
            self._log_debug("Spectrogram plots are disabled by configuration, skipping plotting of accumulated audio data")

        if self._xconfig.get("speech-to-text.generate_fourier_transform_plots", False):
            self.plot_fourier_transforms(input_signal=np.concatenate(self.accumulated_signal),
                                         filtered_signal=np.concatenate(self.accumulated_filtered_signal if preprocessor_enabled else self.accumulated_signal))
        else:
            self._log_debug("Fourier transform plots are disabled by configuration, skipping plotting of accumulated audio data")
    
    # ------ Actual work --------
    
    def plot_signals(self, input_signal: np.ndarray = None, filtered_signal: np.ndarray = None):

        if self._xconfig.get("speech-to-text.generate_signal_plots", False):
            preprocessor_enabled = self._xconfig.get("speech-to-text.preprocessor.enabled", False)

            audio_graph = AudioGraph(config=self._xconfig, params=self._xparams)
            audio_graph.plot_waveform_comparison(
                input_signal,
                filtered_signal, 
                self.samplerate, 
                filepath=self.signal_plots_path,
                # filename=self.signal_plots_path_name % Xtime.now_key(),
                filename=self.signal_plots_path_name % Xtime.now_key() \
                    if self.unified_timestamp_key is None \
                        else self.signal_plots_path_name % self.unified_timestamp_key,
                also_latest=True,
                main_title=f"Original vs {'(Disabled) ' if not preprocessor_enabled else ''}Filtered Audio Signal - {Xtime.current_time_str() \
                    if self.unified_timestamp_str is None \
                    else self.unified_timestamp_str}",
                signal_name_1=f"Original at {self.input_samplerate} Hz",
                signal_name_2=f"{'(Disabled) ' if not preprocessor_enabled else ''}Butterworth bandpass {self.lowcut_freq}-{self.highcut_freq} Hz")

            self._log_debug(f"🗣️ 📈 Plotted audio segment at: {os.path.join(self.signal_plots_path, self.signal_plots_path_name_latest)}")
    
    def plot_spectograms(self, input_signal: np.ndarray = None, filtered_signal: np.ndarray = None):

        if self._xconfig.get("speech-to-text.generate_spectrogram_plots", False):
            preprocessor_enabled = self._xconfig.get("speech-to-text.preprocessor.enabled", False)

            audio_graph = AudioGraph(config=self._xconfig, params=self._xparams)
            audio_graph.plot_spectrogram_comparison(
                input_signal,
                filtered_signal, 
                self.samplerate, 
                filepath=self.spectrograms_plots_path,
                filename=self.spectrograms_plots_path_name % Xtime.now_key() \
                    if self.unified_timestamp_key is None \
                        else self.spectrograms_plots_path_name % self.unified_timestamp_key,
                also_latest=True,
                main_title="Input Audio Spectrogram",
                signal_name_1=f"Original at {self.input_samplerate} Hz  - {Xtime.current_time_str()}" \
                    if self.unified_timestamp_str is None \
                        else f"Original at {self.input_samplerate} Hz  - {self.unified_timestamp_str}",
                signal_name_2=f"{'(Disabled) ' if not preprocessor_enabled else ''}Butterworth bandpass {self.lowcut_freq}-{self.highcut_freq} Hz")

            self._log_debug(f"🗣️ 📈 Plotted audio spectrogram segment at: {os.path.join(self.spectrograms_plots_path, self.spectrograms_plots_path_name_latest)}")
    
    def plot_fourier_transforms(self, input_signal: np.ndarray = None, filtered_signal: np.ndarray = None):

        if self._xconfig.get("speech-to-text.generate_fourier_transform_plots", False):
            preprocessor_enabled = self._xconfig.get("speech-to-text.preprocessor.enabled", False)

            audio_graph = AudioGraph(config=self._xconfig, params=self._xparams)
            audio_graph.plot_fourier_transform_comparison(
                input_signal,
                filtered_signal, 
                self.samplerate, 
                filepath=self.fourier_transform_plots_path,
                filename=self.fourier_transform_plots_path_name % Xtime.now_key() \
                    if self.unified_timestamp_key is None \
                        else self.fourier_transform_plots_path_name % self.unified_timestamp_key,
                also_latest=True,
                main_title=f"Input Audio Fourier Transform - {Xtime.current_time_str()}" \
                    if self.unified_timestamp_str is None \
                        else f"Input Audio Fourier Transform - {self.unified_timestamp_str}",
                signal_name_1=f"Original at {self.input_samplerate} Hz",
                signal_name_2=f"{'(Disabled) ' if not preprocessor_enabled else ''}Butterworth bandpass {self.lowcut_freq}-{self.highcut_freq} Hz")

            self._log_debug(f"🗣️ 📈 Plotted audio fourier transform segment at: {os.path.join(self.fourier_transform_plots_path, self.fourier_transform_plots_path_name_latest)}")

    def save_preprocessed_audio(self, audio_data_np: np.ndarray):
        # Save the preprocessed audio data to a file for debugging purposes
        if self._xconfig.get("speech-to-text.preprocessor.save_preprocessed_audio", False):
            filename = os.path.join(
                self.preprocessed_audio_files_location, 
                f"{self.FILENAME_PREFIX}{Xtime.now_key() if self.unified_timestamp_key is None else self.unified_timestamp_key}{self.FILENAME_EXTENSION}")
            filename_latest = os.path.join(self.preprocessed_audio_files_location, f"_latest{self.FILENAME_EXTENSION}")
            self._save_audio(audio_data_np, self.preprocessing_samplerate, filename, filename_latest)
    
    def save_input_audio(self, audio_data_np: np.ndarray):
        # Save the input audio data to a file for debugging purposes
        if self._xconfig.get("speech-to-text.save_input_audio", False):
            filename = os.path.join(
                self.audio_files_location, 
                f"{self.FILENAME_PREFIX}{Xtime.now_key() if self.unified_timestamp_key is None else self.unified_timestamp_key}{self.FILENAME_EXTENSION}")
            filename_latest = os.path.join(self.audio_files_location, f"_latest{self.FILENAME_EXTENSION}")
            self._save_audio(audio_data_np, self.input_samplerate, filename, filename_latest)
    
    def _save_audio(self, audio_data_np: np.ndarray, samplerate: int, filename: str, filename_latest: str):
        # sf.write(file=filename, samplerate=self.RATE, data=audio_data_np, format="WAV", subtype="PCM_16")
        io.wavfile.write(filename, samplerate, audio_data_np)
        if os.path.exists(filename_latest):
            os.remove(filename_latest)
        # sf.write(file=filename_latest, samplerate=self.RATE, data=audio_data_np, format="WAV", subtype="PCM_16")
        audio_data_np.nbytes
        io.wavfile.write(filename_latest, samplerate, audio_data_np)
        self._xlog.debug(f"💾 Dumped audio [{audio_data_np.nbytes} bytes] of [{audio_data_np.dtype}] at [{samplerate} Hz] to file: {filename}")
    