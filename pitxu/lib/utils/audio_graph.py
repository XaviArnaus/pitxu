
from pyxavi import Storage, Config, Dictionary, dd

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.xtime import Xtime

from matplotlib import pyplot as plt
import numpy as np
from scipy.fftpack import fft
from scipy.io import wavfile
from scipy import signal
import os


class AudioGraph(PyXavi):

    default_filename: str = "audio_signal_%s.png"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(AudioGraph, self).init_pyxavi(config=config, params=params)
    
    def plot_signal(self, signal_np: np.ndarray, filepath: str = None, filename: str = None, also_latest: bool = False):

        plt.figure(figsize=(10, 4))
        plt.plot(signal_np)
        plt.title("Audio Signal")
        plt.xlabel("Sample")
        plt.ylabel("Amplitude")
        if filepath:
            self._save_plot(filepath, filename, also_latest)
        else:
            plt.show()
        plt.close()
    
    def plot_signal_comparison(self, 
            signal_np1: np.ndarray, 
            signal_np2: np.ndarray, 
            filepath: str = None, 
            filename: str = None, 
            also_latest: bool = False, 
            main_title: str = "Audio Signal Comparison", 
            signal_name_1: str = "Original", 
            signal_name_2: str = "Processed"):

        plt.figure(figsize=(10, 4))
        plt.plot(signal_np1, label=signal_name_1)
        plt.plot(signal_np2, label=signal_name_2, color='orange', alpha=0.7)
        plt.title(main_title)
        plt.xlabel("Sample")
        plt.ylabel("Amplitude")
        plt.legend()
        if filepath:
            self._save_plot(filepath, filename, also_latest)
        else:
            plt.show()
        plt.close()
    
    def plot_waveform(self, signal_np: np.ndarray, sample_rate: int, filepath: str = None, filename: str = None, also_latest: bool = False):
        plt.figure(figsize=(10, 4))
        time_axis = np.arange(len(signal_np)) / sample_rate
        plt.plot(time_axis, signal_np)
        plt.title("Audio Waveform")
        plt.xlabel("Time (s)")
        plt.ylabel("Amplitude")
        if filepath:
            self._save_plot(filepath, filename, also_latest)
        else:
            plt.show()
        plt.close()
    
    def plot_waveform_comparison(self, 
            signal_np1: np.ndarray, 
            signal_np2: np.ndarray, 
            sample_rate: int, 
            filepath: str = None, 
            filename: str = None, 
            also_latest: bool = False,
            main_title: str = "Audio Waveform Comparison",
            signal_name_1: str = "Original",
            signal_name_2: str = "Processed"
            ):
        plt.figure(figsize=(10, 4))
        time_axis = np.arange(len(signal_np1)) / sample_rate
        plt.plot(time_axis, signal_np1, label=signal_name_1)
        plt.plot(time_axis, signal_np2, label=signal_name_2, color='orange', alpha=0.7)
        plt.title(main_title)
        plt.xlabel("Time (s)")
        plt.ylabel("Amplitude")
        plt.legend()
        if filepath:
            self._save_plot(filepath, filename, also_latest)
        else:
            plt.show()
        plt.close()
    
    def plot_wavefile(self, input_filepath: str, output_filepath: str = None, filename: str = None, also_latest: bool = False):
        sample_rate, signal_np = wavfile.read(input_filepath)
        if output_filepath is None:
            output_filepath = input_filepath.replace(".wav", "_waveform.png")
        self.plot_waveform(signal_np, sample_rate, output_filepath, filename, also_latest)
    
    def plot_spectrogram(self, signal_np: np.ndarray, sample_rate: int, filepath: str = None, filename: str = None, also_latest: bool = False):
        plt.figure(figsize=(10, 4))
        plt.specgram(signal_np, Fs=sample_rate)
        plt.title("Audio Spectrogram")
        plt.xlabel("Time (s)")
        plt.ylabel("Frequency (Hz)")
        if filepath:
            self._save_plot(filepath, filename, also_latest)
        else:
            plt.show()
        plt.close()
    
    def plot_spectrogram_comparison(self, 
            signal_np1: np.ndarray, 
            signal_np2: np.ndarray, 
            sample_rate: int, 
            filepath: str = None, 
            filename: str = None, 
            also_latest: bool = False,
            main_title: str = "Audio Spectrogram Comparison",
            signal_name_1: str = "Original",
            signal_name_2: str = "Processed"
            ):
        # https://dsp.stackexchange.com/questions/82333/performing-stft-after-butterworth-filter-seems-lower-in-resolution
        
        plt.figure(figsize=(10, 8))

        ax1 = plt.subplot(2, 1, 1)
        f, t, Sxx = signal.spectrogram(signal_np1, fs=sample_rate, window='hann', scaling='spectrum')
        with np.errstate(divide='ignore'):
            log = np.log10(Sxx)
        mx = np.abs(10 * log).max()
        plt.pcolormesh(t, f / 1000, 10 * log, shading='gouraud',  vmin=-mx, vmax=mx)
        plt.title(f"{main_title} - {signal_name_1}")
        plt.xlabel("Time (s)")
        plt.ylabel("Frequency (Hz)")

        ax2 = plt.subplot(2, 1, 2, sharex=ax1, sharey=ax1)
        f_1, t_1, Sxx_1 = signal.spectrogram(signal_np2, fs=sample_rate, window='hann', scaling='spectrum')
        with np.errstate(divide='ignore'):
            log_1 = np.log10(Sxx_1)
        plt.pcolormesh(t_1, f_1 / 1000, 10 * log_1, shading='gouraud', vmin=-mx, vmax=mx)
        plt.title(f"{main_title} - {signal_name_2}")
        plt.xlabel("Time (s)")
        plt.ylabel("Frequency (Hz)")

        plt.tight_layout()
        if filepath:
            self._save_plot(filepath, filename, also_latest)
        else:
            plt.show()
        plt.close()
    
    def plot_fourier_transform(self, signal_np: np.ndarray, sample_rate: int, filepath: str = None, filename: str = None, also_latest: bool = False):
        N = len(signal_np)
        T = 1.0 / sample_rate
        yf = fft(signal_np)
        xf = np.linspace(0.0, 1.0/(2.0*T), N//2)
        plt.figure(figsize=(10, 4))
        plt.plot(xf, 2.0/N * np.abs(yf[:N//2]))
        plt.title("Fourier Transform")
        plt.xlabel("Frequency (Hz)")
        plt.ylabel("Magnitude")
        if filepath:
            self._save_plot(filepath, filename, also_latest)
        else:
            plt.show()
        plt.close()
    
    def plot_fourier_transform_comparison(self, 
            signal_np1: np.ndarray, 
            signal_np2: np.ndarray, 
            sample_rate: int, 
            filepath: str = None, 
            filename: str = None, 
            also_latest: bool = False,
            main_title: str = "Fourier Transform Comparison",
            signal_name_1: str = "Original",
            signal_name_2: str = "Processed"
            ):
        N = len(signal_np1)
        T = 1.0 / sample_rate
        yf1 = fft(signal_np1)
        xf1 = np.linspace(0.0, 1.0/(2.0*T), N//2)
        yf2 = fft(signal_np2)
        xf2 = np.linspace(0.0, 1.0/(2.0*T), N//2)
        plt.figure(figsize=(10, 4))
        plt.plot(xf1, 2.0/N * np.abs(yf1[:N//2]), label=signal_name_1)
        plt.plot(xf2, 2.0/N * np.abs(yf2[:N//2]), label=signal_name_2, color='orange', alpha=0.7)
        plt.title(main_title)
        plt.xlabel("Frequency (Hz)")
        plt.ylabel("Magnitude")
        plt.legend()
        if filepath:
            self._save_plot(filepath, filename, also_latest)
        else:
            plt.show()
        plt.close()
    
    def plot_butterworth_filter_response(self, b: np.ndarray, a: np.ndarray, sample_rate: int, filepath: str = None, filename: str = None, also_latest: bool = False):
        # https://stackoverflow.com/questions/12093594/how-to-implement-band-pass-butterworth-filter-with-scipy-signal-butter

        # Adapt this to SOS.
        # w, h = signal.freqz(b, a)
        # plt.figure(figsize=(10, 4))
        # plt.plot(0.5 * sample_rate * w / np.pi, 20 * np.log10(np.abs(h)))
        # plt.title("Butterworth Filter Frequency Response")
        # plt.xlabel("Frequency (Hz)")
        # plt.ylabel("Gain (dB)")
        # plt.grid()
        # if filepath:
        #     self._save_plot(filepath, filename, also_latest)
        # else:
        #     plt.show()
        # plt.close()
        pass
    
    def _save_plot(self, filepath: str, filename: str = None, also_latest: bool = False):
        filename = filename if filename is not None else self.default_filename % Xtime.now()
        filename = filename % Xtime.now_key() if "%s" in filename else filename
        plt.savefig(os.path.join(filepath, filename))
        if also_latest:
            plt.savefig(os.path.join(filepath, "_latest.png"))
