from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager, SHARED_USER_IS_SPEAKING
from pitxu.lib.utils.signal_tools import SignalTools
from pitxu.lib.speech_to_text.preprocess.dumper import Dumper
from pitxu.lib.speech_to_text.preprocess.filters import Filters
from pitxu.lib.speech_to_text.preprocess.conversors import Conversors

import numpy as np
from datetime import datetime
from rms_vad import RmsVAD, VADConfig, compute_energy_db
import logging

class Preprocessor(PyXavi):

    # Desired frequency range for human voice (e.g., telephone band)
    LOWCUT_FREQ = 300  # Hz
    HIGHCUT_FREQ = 3400 # Hz
    FILTER_ORDER = 7   # Order of the filter (higher order means steeper rolloff)

    samplerate = 16000  # Sampling rate

    shared_memory: SharedMemoryManager = None
    dumper: Dumper = None
    filters: Filters = None
    vad: RmsVAD = None

    last_human_speaking_datetime: datetime = None
    
    ENERGY_RATIO_THRESHOLD = 0.9

    # How long to wait after the last detected human speaking before considering that the user has stopped speaking (in seconds)
    SPEAKING_SILENCE_TIMEOUT_SECONDS = 1

    # Control if we're currently in a "speaking" state, which can help to avoid false positives when the user is speaking continuously.
    user_is_speaking: bool = False

    accummulated_signal: list = []
    accummulated_filtered_signal: list = []

    VERBOSE_DEBUG: bool = True
    DEBUG_ENERGY_FACTOR = 1

    def __init__(self, config: Config, params: Dictionary):
        super(Preprocessor, self).init_pyxavi(config=config, params=params)

        self._xlog.info("🎤 Initializing Preprocess for Speech-to-Text")

        if params.key_exists("samplerate"):
            self.samplerate = params.get("samplerate")
        elif self._xconfig.get("speech-to-text.preprocessor.input_samplerate", None) is not None and \
             self._xconfig.get("speech-to-text.preprocessor.input_samplerate", None) > 0:
            self.samplerate = self._xconfig.get("speech-to-text.preprocessor.input_samplerate")
        else:
            self._xlog.warning(f"No samplerate provided in params to Preprocess, using default of {self.samplerate} Hz")
        
        # Initialize the VAD with the provided configuration
        threshold = self._xconfig.get("speech-to-text.vad.threshold", 0.6)
        attack = self._xconfig.get("speech-to-text.vad.attack", 0.2)
        release = self._xconfig.get("speech-to-text.vad.release", 1.5)
        self.vad = RmsVAD(VADConfig(threshold=threshold, attack=attack, release=release, sample_rate=self.samplerate))
        
        self.LOWCUT_FREQ = self._xconfig.get("speech-to-text.preprocessor.lowcut_freq", self.LOWCUT_FREQ)
        self.HIGHCUT_FREQ = self._xconfig.get("speech-to-text.preprocessor.highcut_freq", self.HIGHCUT_FREQ)
        self.FILTER_ORDER = self._xconfig.get("speech-to-text.preprocessor.filter_order", self.FILTER_ORDER)
        self.SPEAKING_SILENCE_TIMEOUT_SECONDS = self._xconfig.get("speech-to-text.preprocessor.silence_timeout_seconds", self.SPEAKING_SILENCE_TIMEOUT_SECONDS)

        # self.shared_memory = SharedMemoryManager(config=config, params=params)
        # self.shared_memory.initialize_existing_shared_memory_flags()

        params.set("samplerate", self.samplerate)
        params.set("lowcut_freq", self.LOWCUT_FREQ)
        params.set("highcut_freq", self.HIGHCUT_FREQ)
        params.set("order", self.FILTER_ORDER)

        self.filters = Filters(config=config, params=params)
        self.dumper = Dumper(config=config, params=params)

        logging.getLogger("matplotlib").setLevel(self._xconfig.get("libs_logger.matplotlib.loglevel", logging.WARNING))

        self.log_summary("Preprocessor Initialization", [
            ("Low cut freq", f"{self.LOWCUT_FREQ} Hz"),
            ("High cut freq", f"{self.HIGHCUT_FREQ} Hz"),
            ("Filter order", f"{self.FILTER_ORDER}"),
            ("Samplerate", f"{self.samplerate} Hz"),
            ("Speaking silence timeout", f"{self.SPEAKING_SILENCE_TIMEOUT_SECONDS} seconds"),
            ("VAD Threshold", threshold),
            ("VAD Attack", f"{attack} seconds"),
            ("VAD Release", f"{release} seconds")
        ])

        self._log_debug("🎤 Done Initializing Preprocess for Speech-to-Text")
    
    def preprocess_chunk(self, indata: bytes) -> bytes | None:
        # Stop a second and ready this:
        # https://github.com/pipecat-ai/pipecat/issues/1653#issuecomment-3021647937

        # What we receive from the STT queue are raw (non-numpy) bytes in int16 dtype format.
        # What is needed for preprocessing and so on are numpy arrays
        # Ensure that what we return here are bytes in int16!
        # self._xlog.debug(f"🎤 Preprocess: Received audio chunk of {len(indata)} bytes for preprocessing.")

        # All operations are done with numpy arrays for performance reasons, so convert it first.
        # We work here internally with INT16 (PCM_16) format.
        audio_data_np = Conversors.byte_chunk_to_numpy_array(indata)

        # We want to work with mono audio. If comes as stereo, convert it to mono.
        audio_data_np = Conversors.stereo_to_mono(audio_data_np)

        # Apply bandpass filter to isolate human voice frequencies
        filtered_audio_np = self.filters.bandpass_filter(audio_data_np, normalize_filtered_outcome=False)
        # filtered_audio_np = self.filters.fftBandpass(filtered_audio_np, 0.5*self.LOWCUT_FREQ, 1.5 *self.HIGHCUT_FREQ, fs=self.samplerate)

        # Maintain the accummulators
        self.add_to_accumulated_signal_np(audio_data_np, filtered_audio_np)

        return Conversors.numpy_array_to_byte_chunk(filtered_audio_np)

        # All calculations are done with numpy arrays for performance reasons, so convert it first.
        audio_data_np = Conversors.byte_chunk_to_numpy_array(indata)

        # Apply bandpass filter to isolate human voice frequencies
        filtered_audio_np = self.bandpass_filter(audio_data_np)
        filtered_audio_in_bytes = Conversors.numpy_array_to_byte_chunk(filtered_audio_np)

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

        self.dumper.plot_signals(input_signal, filtered_signal)
        self.dumper.plot_spectograms(input_signal, filtered_signal)
        self.dumper.plot_fourier_transforms(input_signal, filtered_signal)

        self.dumper.save_input_audio(input_signal)
        self.dumper.save_preprocessed_audio(filtered_signal)
        self.accummulated_signal = []
        self.accummulated_filtered_signal = []

        self._log_debug(f"🗣️ End speaking 🏁")

    def is_vad_speech(self, chunk: bytes) -> bool:
        # This is a simple wrapper around the VAD to check if the chunk contains speech.
        # It can be used as an additional check before doing more expensive calculations like energy analysis.

        # NOT USED

        events = self.vad.feed(chunk)
        dd(events)
        is_speech = self.vad.is_speaking
        self.vad.reset()
        return is_speech
    
    def add_to_accumulated_signal(self, signal_chunk: bytes, filtered_signal_chunk: bytes):
        signal_chunk_np = Conversors.byte_chunk_to_numpy_array(signal_chunk)
        filtered_signal_chunk_np = Conversors.byte_chunk_to_numpy_array(filtered_signal_chunk)
        self.add_to_accumulated_signal_np(signal_chunk_np, filtered_signal_chunk_np)
    
    def add_to_accumulated_signal_np(self, signal_chunk: np.ndarray, filtered_signal_chunk: np.ndarray):
        self.accummulated_signal.append(signal_chunk)
        self.accummulated_filtered_signal.append(filtered_signal_chunk)

    def get_energy_ratio(self, audio_buffer: np.ndarray) -> float:
        """
        Calculate the ratio of energy in the human voice frequency range to the total energy of the audio signal.

        NOT USED

        Parameters:
        audio_buffer (np.ndarray): The input audio data.

        Returns:
        float: The ratio of energy in the human voice frequency range to the total energy.
        """
        # This approach uses Discrete Fourier Transform to calculate the energy of the signal across different frequencies.
        # This means that we have energy per frequency.
        energy_per_frequencies = SignalTools.energy(audio_buffer, self.samplerate)

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

        NOT USED
        """
        return self.shared_memory.read_shared_memory_flag(SHARED_USER_IS_SPEAKING)
    
    def is_beyond_silence_threshold(self, silence_timeout_seconds: int = SPEAKING_SILENCE_TIMEOUT_SECONDS) -> bool:
        '''
        Checks if the user should be considered as not speaking anymore, based on the last time we detected human speaking and a silence timeout.
        This can be used to automatically unset the "user is speaking" state after a certain period of silence, which can help to keep the state accurate without requiring explicit signals for when the user stops speaking.

        NOT USED
        '''
        if self.last_human_speaking_datetime is not None:
            time_since_last_speaking = (datetime.now() - self.last_human_speaking_datetime).total_seconds()
            if time_since_last_speaking > silence_timeout_seconds:
                return True
        return False
    
    # Bandpass is filtering too much the sibilance ("s" sounds)? Here's how to fix it:
    # -------------------------------------------------------------------------------
    
    # If a bandpass filter is attenuating sibilance (the harsh "s," "sh," and "t" sounds, typically between 4 kHz and 10 kHz) too much, the filter is likely too narrow or improperly centered. To fix this, you need to adjust the filter to be less invasive. 

    # Here are specific ways to address this issue:
    # 1. Widen the Bandwidth (Q Factor) 
    # Problem: If the "Q" (bandwidth) of the bandpass filter is too narrow, it acts like a notch filter, killing the sound.
    # Solution: Decrease the Q factor (widen the bandwidth). A wider band will allow more of the surrounding frequencies to pass through, making the attenuation less noticeable and more natural. 

    # 2. Shift the Center Frequency
    # Problem: The filter center frequency might be directly on top of the loudest part of the sibilance, or perhaps too low, affecting the mid-range frequencies of the voice.
    # Solution: Adjust the center frequency to be more precise to the specific "s" sound. Sibilance often lives between 4-7 kHz; sweep this range to find the exact spot that needs attenuation without affecting the overall vocal tone. 

    # 3. Reduce the Gain Reduction/Attenuate Less 
    # Problem: You are reducing the volume of that frequency range too aggressively.
    # Solution: Reduce the gain reduction amount. In a parametric EQ or dynamic EQ, turn down the amount of attenuation (e.g., from -10dB to -3dB). 

    # 4. Switch to a De-Esser (Dynamic Approach) 
    # Why: A bandpass filter is static, meaning it cuts the frequency all the time. A De-Esser is a dynamic processor, meaning it only acts when the "s" sound crosses a certain volume threshold.
    # Action: Insert a De-Esser and set the frequency range to 5–8 kHz. This will only tame the sharp sounds while leaving the rest of the audio untouched. 

    # 5. Use Parallel Processing (Sidechaining) 
    # Action: Send your vocal to a bus, apply the bandpass filter to that bus (making it very harsh/hollow), and then mix that filtered signal underneath your original vocal. This allows you to blend the filtered, de-sibilanced sound with the original, controlled sound. 

    # Also: https://www.reddit.com/r/WeAreTheMusicMakers/comments/1094otc/sibilance_is_killing_me/