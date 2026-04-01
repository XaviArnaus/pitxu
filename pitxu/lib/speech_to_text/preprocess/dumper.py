from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.utils.xtime import Xtime
from pitxu.lib.utils.audio_graph import AudioGraph

from scipy import io
import numpy as np
import os
import soundfile as sf


class Dumper(PyXavi):

    audio_graph: AudioGraph = None

    samplerate: int = 16000
    lowcut_freq: int = 300
    highcut_freq: int = 3400

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

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config, params: Dictionary):
        super(Dumper, self).init_pyxavi(config=config, params=params)

        self._xlog.info("🎤 Initializing Audio Dumper for Speech-to-Text")

        self.samplerate = params.get("samplerate", self.samplerate)
        self.lowcut_freq = params.get("lowcut_freq", self.lowcut_freq)
        self.highcut_freq = params.get("highcut_freq", self.highcut_freq)

        self._prepare_dump_audio_files()
        
        self._log_debug("🎤 Done Initializing Audio Dumper for Speech-to-Text")
    
    def _prepare_dump_audio_files(self):

        self.signal_plots_path = os.path.join(self._xconfig.get("storage.path"), self.signal_plots_path)
        self.spectrograms_plots_path = os.path.join(self._xconfig.get("storage.path"), self.spectrograms_plots_path)
        self.fourier_transform_plots_path = os.path.join(self._xconfig.get("storage.path"), self.fourier_transform_plots_path)

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
    
    def plot_signals(self, input_signal: np.ndarray = None, filtered_signal: np.ndarray = None):

        if self._xconfig.get("speech-to-text.generate_signal_plots", False):
            audio_graph = AudioGraph(config=self._xconfig, params=self._xparams)
            audio_graph.plot_waveform_comparison(
                input_signal,
                filtered_signal, 
                self.samplerate, 
                filepath=self.signal_plots_path,
                filename=self.signal_plots_path_name % Xtime.now_key(),
                also_latest=True,
                main_title=f"Original vs Filtered Audio Signal - {Xtime.current_time_str()}",
                signal_name_1=f"Original at {self.samplerate} Hz",
                signal_name_2=f"Butterworth bandpass {self.lowcut_freq}-{self.highcut_freq} Hz")

            self._log_debug(f"🗣️ 📈 Plotted audio segment at: {os.path.join(self.signal_plots_path, self.signal_plots_path_name_latest)}")
    
    def plot_spectograms(self, input_signal: np.ndarray = None, filtered_signal: np.ndarray = None):

        if self._xconfig.get("speech-to-text.generate_spectrogram_plots", False):
            audio_graph = AudioGraph(config=self._xconfig, params=self._xparams)
            audio_graph.plot_spectrogram_comparison(
                input_signal,
                filtered_signal, 
                self.samplerate, 
                filepath=self.spectrograms_plots_path,
                filename=self.spectrograms_plots_path_name % Xtime.now_key(),
                also_latest=True,
                main_title="Input Audio Spectrogram",
                signal_name_1=f"Original at {self.samplerate} Hz  - {Xtime.current_time_str()}",
                signal_name_2=f"Butterworth bandpass {self.lowcut_freq}-{self.highcut_freq} Hz")

            self._log_debug(f"🗣️ 📈 Plotted audio spectrogram segment at: {os.path.join(self.spectrograms_plots_path, self.spectrograms_plots_path_name_latest)}")
    
    def plot_fourier_transforms(self, input_signal: np.ndarray = None, filtered_signal: np.ndarray = None):

        if self._xconfig.get("speech-to-text.generate_fourier_transform_plots", False):
            audio_graph = AudioGraph(config=self._xconfig, params=self._xparams)
            audio_graph.plot_fourier_transform_comparison(
                input_signal,
                filtered_signal, 
                self.samplerate, 
                filepath=self.fourier_transform_plots_path,
                filename=self.fourier_transform_plots_path_name % Xtime.now_key(),
                also_latest=True,
                main_title=f"Input Audio Fourier Transform - {Xtime.current_time_str()}",
                signal_name_1=f"Original at {self.samplerate} Hz",
                signal_name_2=f"Butterworth bandpass {self.lowcut_freq}-{self.highcut_freq} Hz")

            self._log_debug(f"🗣️ 📈 Plotted audio fourier transform segment at: {os.path.join(self.fourier_transform_plots_path, self.fourier_transform_plots_path_name_latest)}")
    

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
        io.wavfile.write(filename, self.samplerate, audio_data_np)
        if os.path.exists(filename_latest):
            os.remove(filename_latest)
        # sf.write(file=filename_latest, samplerate=self.RATE, data=audio_data_np, format="WAV", subtype="PCM_16")
        audio_data_np.nbytes
        io.wavfile.write(filename_latest, self.samplerate, audio_data_np)
        self._xlog.debug(f"💾 Dumped audio [{audio_data_np.nbytes} bytes] of [{audio_data_np.dtype}] to file: {filename}")
    