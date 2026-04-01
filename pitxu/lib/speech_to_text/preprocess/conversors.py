import numpy as np
from scipy.signal import resample_poly
import math
import samplerate

class Conversors:

    @staticmethod
    def byte_chunk_to_numpy_array(byte_chunk: bytes) -> np.ndarray:
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
    
    @staticmethod
    def numpy_array_to_byte_chunk(audio_array: np.ndarray) -> bytes:
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
    
    @staticmethod
    def stereo_to_mono(audio_array: np.ndarray) -> np.ndarray:
        """
        Convert a stereo audio array to mono by averaging the two channels.

        Parameters:
        audio_array (np.ndarray): The input stereo audio array with shape (n_samples, 2).

        Returns:
        np.ndarray: The converted mono audio array with shape (n_samples,).
        """
        if len(audio_array.shape) == 2 and audio_array.shape[1] == 2:
            # mono_audio = audio_array.mean(axis=1).astype(np.int16)
            # mono_audio = audio_array.reshape(-1, 2).mean(axis=1)
            mono_audio = audio_array.reshape(-1, 2)
            return mono_audio
        elif len(audio_array.shape) == 1:
            return audio_array
        else:
            raise ValueError("Input audio array must be stereo with shape (n_samples, 2) or mono with shape (n_samples,).")
    
    @staticmethod
    def resample_audio_scikit(resampler: samplerate.Resampler, audio: bytes, in_rate: int, out_rate: int) -> bytes:
        if in_rate == out_rate:
            return audio
        
        audio_data = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
        
        resampled_audio = resampler.process(audio_data, out_rate / in_rate)
        
        # Clip and convert
        resampled_audio = np.clip(resampled_audio, -32768, 32767)
        result = resampled_audio.astype(np.int16).tobytes()
        
        return result
    
    @staticmethod
    def resample_audio_interpolation(audio: bytes, in_rate: int, out_rate: int) -> bytes:
        # https://github.com/nwhitehead/swmixer/blob/master/swmixer.py
        # https://stackoverflow.com/questions/51420923/resampling-a-signal-with-scipy-signal-resample
        if in_rate == out_rate:
            return audio
        
        audio_data = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
        
        scale = out_rate / in_rate
        # calculate new length of sample
        n = round(len(audio_data) * scale)

        # use linear interpolation
        # endpoint keyword means than linspace doesn't go all the way to 1.0
        # If it did, there are some off-by-one errors
        # e.g. scale=2.0, [1,2,3] should go to [1,1.5,2,2.5,3,3]
        # but with endpoint=True, we get [1,1.4,1.8,2.2,2.6,3]
        # Both are OK, but since resampling will often involve
        # exact ratios (i.e. for 44100 to 22050 or vice versa)
        # using endpoint=False gets less noise in the resampled sound
        resampled_signal = np.interp(
            np.linspace(0.0, 1.0, n, endpoint=False),  # where to interpret
            np.linspace(0.0, 1.0, len(audio_data), endpoint=False),  # known positions
            audio_data,  # known data points
        )
        
        # Clip and convert
        resampled_audio = np.clip(resampled_signal, -32768, 32767)
        # resampled_audio = np.clip((resampled_audio * 32768.0).round(), -32768, 32767)
        result = resampled_audio.astype(np.int16).tobytes()
        
        return result
    
    @staticmethod
    def resample_audio_polyphase(audio: bytes, in_rate: int, out_rate: int) -> bytes:
        if in_rate == out_rate:
            return audio
        
        audio_data = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
        
        # Find GCD for rational resampling
        gcd = math.gcd(in_rate, out_rate)
        up = out_rate // gcd
        down = in_rate // gcd
        
        # Resample with automatic anti-aliasing filter
        resampled_audio = resample_poly(audio_data, up, down)
        
        # Clip and convert
        resampled_audio = np.clip(resampled_audio, -32768, 32767)
        # resampled_audio = np.clip((resampled_audio * 32768.0).round(), -32768, 32767)
        result = resampled_audio.astype(np.int16).tobytes()
        
        return result