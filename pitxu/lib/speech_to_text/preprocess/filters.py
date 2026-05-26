from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.utils.signal_tools import SignalTools

from scipy import signal
import numpy as np
import numpy.fft as fft


class Filters(PyXavi):

    samplerate: int = 16000
    lowcut_freq: int = 300
    highcut_freq: int = 3400
    order: int = 2

    signal_filter: np.ndarray = None

    # Weight for the new energy value in the moving average calculation (between 0 and 1)
    # A higher weight means that the average will react more quickly to changes in energy,
    # while a lower weight means that the average will be more stable and less affected by short-term fluctuations.
    NEW_ENERGY_WEIGHT = 0.1
    
    ENERGY_RATIO_THRESHOLD = 0.9

    # How long to wait after the last detected human speaking before considering that the user has stopped speaking (in seconds)
    SPEAKING_SILENCE_TIMEOUT_SECONDS = 1

    VERBOSE_DEBUG: bool = True
    DEBUG_ENERGY_FACTOR = 1

    def __init__(self, config: Config, params: Dictionary):
        super(Filters, self).init_pyxavi(config=config, params=params)

        self._xlog.info("Initializing Filters for Speech-to-Text")

        self.lowcut_freq = params.get("audio_parameters.filter_lowcut_freq", self.lowcut_freq)
        self.highcut_freq = params.get("audio_parameters.filter_highcut_freq", self.highcut_freq)
        self.order = params.get("audio_parameters.filter_order", self.order)
        self.samplerate = params.get("audio_parameters.preprocessing_samplerate", self.samplerate)
        
        self.SPEAKING_SILENCE_TIMEOUT_SECONDS = self._xconfig.get("speech-to-text.preprocessor.silence_timeout_seconds", self.SPEAKING_SILENCE_TIMEOUT_SECONDS)

        self.signal_filter = self.butter_filter_design_simple()

        self.log_summary("Audio Filter Initialization", [
            ("Low cut freq", f"{self.lowcut_freq} Hz"),
            ("High cut freq", f"{self.highcut_freq} Hz"),
            ("Filter order", f"{self.order}"),
            ("Samplerate", f"{self.samplerate} Hz"),
            ("Speaking silence timeout", f"{self.SPEAKING_SILENCE_TIMEOUT_SECONDS} seconds")
        ])

        self._log_debug("Done Initializing Filters for Speech-to-Text")
    
    # --- Signal calculations ---

    def butter_filter_design(self) -> np.ndarray:

        # Design the Butterworth bandpass filter
        # nyquist = 0.5 * self.samplerate
        # low = self.lowcut_freq / nyquist
        # high = self.highcut_freq / nyquist
        # b, a = signal.butter(self.FILTER_ORDER, [low, high], btype='band')
        # sos = signal.butter(self.FILTER_ORDER, [low, high], btype='band', output='sos', fs=self.samplerate)
        # sos = signal.butter(self.FILTER_ORDER, [low, high], btype='band', analog=True, output='sos')
        # sos = signal.butter(self.FILTER_ORDER, [low, high], btype='band', analog=False, output='sos', fs=self.samplerate)

        filter_params = {
            # For human voice processing at a 16 kHz sampling rate (wideband speech),
            # the optimal filter configuration typically aims to pass the essential voice spectrum 
            # while attenuating noise and preventing aliasing.
            #
            # 1. Passband Frequencies (0 dB Gain)
            #     - Optimal Range: 100 Hz – 7000 Hz.
            #     - Key Speech Frequencies: 300 Hz – 3400 Hz is considered the core for intelligibility, while 50 Hz – 7000 Hz covers the full spectrum of high-quality wideband speech.
            #     - Passband Gain: Ideally flat (0 dB) to avoid spectral distortion.
            #     - Passband Ripple: Typically < 1 dB or tighter, such as 0.015 dB for high-precision filters.
            # 2. Stopband Frequencies & Attenuation
            #     - Lower Stopband: Below 50 Hz (to remove rumble).
            #     - Upper Stopband: Above 8000 Hz (Nyquist frequency).
            #     - Stopband Attenuation: A minimum of 39 dB to 60 dB is recommended to remove out-of-band noise. 

            # Summary of Filter Specification (16 kHz Sample Rate)
            #     Parameter 	    Frequency Range	    Gain/Attenuation
            #     ----------------------------------------------------
            #     Passband	        100 Hz – 7 kHz	    0 dB (Flat)
            #     Transition Band	7 kHz – 8 kHz	    Roll-off
            #     Stopband	        > 8 kHz	            -40 to -60 dB

            # Key Considerations
            #     16 kHz Sampling: A 16 kHz sampling rate allows for a maximum Nyquist frequency of 8 kHz (16/2). This captures speech with high naturalness, far superior to 8 kHz telephone audio.
            #     High-Frequency Information: While 3–4 kHz is sufficient for comprehension, the 5–8 kHz range contains sibilants ("s", "sh") and breath sounds, which are crucial for natural sounding voice, rather than just raw intelligibility.
            #     Avoid Excessive Boosting: Boosting 7 kHz and above can lead to undesirable sibilance (harsh "S" sounds).
            16000: {
                "passband": {
                    "low_freq": 300,
                    "high_freq": 3400,
                    "gain": 0.015
                },
                "stopband": {
                    "low_freq": 50,
                    "high_freq": 8000,
                    "gain": 40.0
                },
            },
            # For high-quality, professional audio applications (such as film, TV, and studio voiceover) recorded at a 48 kHz sampling rate, the 24 kHz Nyquist frequency allows for a full, natural voice reproduction without aliasing. Human voice has fundamental frequencies from 100Hz to 900Hz and harmonics ranging up to 17kHz or higher. 
            #
            # Recommended Filter Specifications for Human Voice (48 kHz Sample Rate) 
            #     - Passband (Frequencies to keep): 50 Hz – 15 kHz to 20 kHz.
            #         - Voice Over/Dialog: Often focuses on intelligibility, passing up to 15 kHz.
            #         - Professional Audio: Usually passes up to 20 kHz to capture all nuances of the voice.
            #     - Passband Gain: Ideally flat (0 dB) to preserve natural tone, or slightly boosted for presence (e.g., +2 dB at 3 kHz).
            #     - Stopband Frequencies (Frequencies to eliminate):
            #         - Low End: Below 50 Hz – 80 Hz (used to remove microphone rumble/plosives).
            #         - High End: Above 22 kHz – 24 kHz (to prevent aliasing near the Nyquist frequency).
            #     - Stopband Gain (Attenuation): A minimum of 60 dB to 100 dB of attenuation is typical to ensure noise is completely eliminated. 
            #
            # Typical Filtering Approaches
            #     - High-Pass (Low Cut): Cut frequencies below 50–80 Hz with a slope of 12 dB or 24 dB/octave to remove "mud" and rumble.
            #     - Low-Pass (High Cut): While the human voice has few audible harmonics above 15 kHz, applying a low-pass filter around 20–22 kHz ensures that any ultra-high frequencies do not cause aliasing, leaving a 2 kHz-4 kHz guard band before the Nyquist limit.
            #
            # Summary of Filter Specification (16 kHz Sample Rate)
            #     Parameter 	    Frequency Range	    Gain/Attenuation
            #     ----------------------------------------------------
            #     Passband	        50 Hz – 15 kHz	    0 dB (Flat) or 2 dB boost at 3 kHz
            #     Transition Band	15 kHz – 20 kHz	    Roll-off
            #     Stopband	        > 22 kHz	        -46 to -100 dB
            #
            # Note: 48 kHz sampling allows for a gentle anti-aliasing filter to be used without affecting the audible range below 20 kHz, unlike 44.1 kHz, which requires a much steeper filter that can affect the highest audible frequencies.
            48000: {
                # This setup didn't work.
                # "passband": {
                #     "low_freq": 50,
                #     "high_freq": 15000,
                #     "gain": 0.015
                # },
                # "stopband": {
                #     "low_freq": 49,
                #     "high_freq": 22000,
                #     "gain": 80.0
                # }
                "passband": {
                    "low_freq": self.lowcut_freq,
                    "high_freq": self.highcut_freq,
                    "gain": 0.015
                },
                "stopband": {
                    "low_freq": 0.8*self.lowcut_freq,
                    "high_freq": 1.2*self.highcut_freq,
                    "gain": 90.0
                }
            },
            # Default for unidentified frequencies
            99999: {
                "passband": {
                    "low_freq": self.lowcut_freq,
                    "high_freq": self.highcut_freq,
                    "gain": 60.0
                },
                "stopband": {
                    "low_freq": 0.8*self.lowcut_freq,
                    "high_freq": 1.2*self.highcut_freq,
                    "gain": 80.0
                }
            }
        }

        params = {}
        if self.samplerate not in filter_params:
            self._xlog.warning(f"No specific filter parameters found for sample rate {self.samplerate} Hz, using default settings.")
            params = filter_params[99999]
        else:
            self._log_debug(f"Using specific filter parameters for sample rate {self.samplerate} Hz.")
            params = filter_params[self.samplerate]
        
        # params = filter_params[99999]

        nyquist = 2 / self.samplerate
        passband_low_freq = params["passband"]["low_freq"]
        passband_high_freq = params["passband"]["high_freq"]
        passband_gain = params["passband"]["gain"]
        stopband_low_freq = params["stopband"]["low_freq"]
        stopband_high_freq = params["stopband"]["high_freq"]
        stopband_gain = params["stopband"]["gain"]

        passband_freqs = np.array([passband_low_freq, passband_high_freq])*nyquist  # normalized pass band frequnecies
        stopband_freqs = np.array([stopband_low_freq, stopband_high_freq])*nyquist  # normalized stop band frequencies

        # Pre-normalization of the audio data can help to improve the performance of the filter and prevent issues with clipping or numerical instability during filtering.
        # max_val = np.max(np.abs(audio_data_np))
        # if max_val > 0:
        #     audio_data_np = audio_data_np / max_val
        # Once the recording is in memory, we normalise it to +1/-1
        # x /= np.max(np.abs(x)) ## This is sensitive to outliers and rescaling is not consistent
        # audio_data_np /= audio_data_np.std()

        analog = False
        output_format = "sos"

        self.log_summary("Butterworth Filter Design", [
            ("Sample Rate", f"{self.samplerate} Hz"),
            ("Passband Frequencies", f"{passband_low_freq} Hz - {passband_high_freq} Hz"),
            ("Passband Gain", f"{passband_gain} dB"),
            ("Stopband Frequencies", f"{stopband_low_freq} Hz - {stopband_high_freq} Hz"),
            ("Stopband Gain (Attenuation)", f"{stopband_gain} dB"),
            ("Analog filter?", f"{analog}"),
            ("Output filter format", f"{output_format}")
        ])

        # Design the Butterworth bandpass filter using second-order sections for numerical stability
        # The `iirdesign` function allows us to specify the passband and stopband frequencies and the desired gains.
        # https://dsp.stackexchange.com/questions/82333/performing-stft-after-butterworth-filter-seems-lower-in-resolution
        return signal.iirdesign(
                    wp=passband_freqs, 
                    ws=stopband_freqs, 
                    gpass=passband_gain, 
                    gstop=stopband_gain, 
                    ftype="butter", 
                    analog=analog,
                    output=output_format)
    
    def butter_filter_design_simple(self) -> np.ndarray:
        nyquist = 0.5 * self.samplerate
        low = self.lowcut_freq / nyquist
        high = self.highcut_freq / nyquist
        # Most likely this IF should not be here
        if high >= 1.0:
            self._xlog.warning(f"High cut frequency {self.highcut_freq} Hz is above Nyquist frequency for samplerate {self.samplerate} Hz, adjusting to {0.99} Hz.")
            high = 0.99
        sos = signal.butter(self.order, [low, high], btype='band', analog=False, output='sos')

        self.log_summary("Butterworth Filter Design", [
            ("Sample Rate", f"{self.samplerate} Hz"),
            ("Bandpass Frequencies", f"{self.lowcut_freq} Hz - {self.highcut_freq} Hz"),
            ("Bandpass order", f"{self.order}"),
            ("Analog filter?", f"{False}"),
            ("Output filter format", "sos")
        ])

        return sos
    
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

        # Convert to float for filtering (important for signal processing)
        # audio_data_np = SignalTools.float32(audio_data_np)
        audio_data_np = audio_data_np.astype(np.float32)

        # Apply the filter to the audio data.
        # Attention, it returns float64
        # filtered_audio_np = signal.lfilter(b, a, audio_data_np)
        # filtered_audio_np = signal.sosfiltfilt(sos, audio_data_np, padlen=len(audio_data_np) - 1)
        # filtered_audio_np = signal.sosfilt(sos, audio_data_np)

        # This kinda works, just that the output is robotic.
        # zi = signal.sosfilt_zi(sos)
        # filtered_audio_np, zf = signal.sosfilt(sos, audio_data_np, zi=zi*audio_data_np[0])

        # self._log_debug("5. filter pre sosfiltfilt:")
        # dd(audio_data_np.shape)
        # dd(audio_data_np.dtype)
        # dd(audio_data_np.ndim)

        filtered_audio_np = signal.sosfiltfilt(self.signal_filter, audio_data_np, padlen=len(audio_data_np) - 1)

        # Normalize the filtered audio to prevent clipping and ensure it stays within the int16 range
        if normalize_filtered_outcome:
            max_val = np.max(np.abs(filtered_audio_np))
            if max_val > 0:
                filtered_audio_np = filtered_audio_np / max_val
        
        # These 2 are supposed to keep the quality in the conversion to int16,
        # but the signal appears saturated in the graphs.
        # -->
        
        # I've read to always clip the values before converting to int16, to avoid wrap-around issues.
        # Clipping is the process of limiting the amplitude of a signal to a specified range.
        # filtered_audio_np = np.clip((filtered_audio_np * 32768.0).round(), -32768, 32767)

        # Convert back this audio so the further operations find the common ground
        # filtered_audio_np = (filtered_audio_np * (2**15 - 1)).clip(-32768, 32767)
        # filtered_audio_np = SignalTools.int16(filtered_audio_np)
        # <--

        filtered_audio_np = filtered_audio_np.astype(np.int16)

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
        filtered = fft.irfft(xf, len(x))
        return filtered.astype(np.int16)

        # These 2 are supposed to keep the quality in the conversion to int16,
        # but the signal appears saturated in the graphs.
        # filtered = np.clip((filtered * 32768.0).round(), -32768, 32767)
        # return SignalTools.int16(filtered)

    def scope_to_frequency_domain(self, audio_data_np: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """
        Convert the audio data from the time domain to the frequency domain.

        Parameters
        ----------
        audio_data_np : np.ndarray
            Input audio data in the time domain.

        Returns
        -------
        freqs : np.ndarray
            Array of frequency bins.
        spectrum : np.ndarray
            Magnitude spectrum of the audio data.
        """
        spectrum = np.abs(fft.rfft(audio_data_np))
        freqs = fft.rfftfreq(len(audio_data_np), d=1 / self.samplerate)
        return freqs, spectrum

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
    