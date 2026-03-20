import numpy as np
from scipy.signal import resample_poly
import math

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
    def resample_audio(audio: bytes, in_rate: int, out_rate: int) -> bytes:
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