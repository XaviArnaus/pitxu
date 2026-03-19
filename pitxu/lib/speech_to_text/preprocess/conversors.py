import numpy as np

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