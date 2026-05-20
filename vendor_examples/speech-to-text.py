# This won't work in a system without a Numpy dependency installed.
# The main application does not use it.
#
# Still, the Numpy here is used to recognise that the user is speaking
# by calculating the energy of the voice in the environment. May be cool.
#
# Tradeoff is that numpy fails to install (smoothly) into the Raspberry Pi OS
# Did not invest more after discovering that it's only used in this example.

import pyaudio
import numpy as np
from vosk import Model, KaldiRecognizer
import json
import time

# Path to the Vosk model directory
model_path = "./model"  # Replace with your model path

# Load the Vosk model
model = Model(model_path + "/vosk-model-small-en-us-0.15")

# Audio settings
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
INITIAL_CHUNK = 1024  # Starting chunk size
MIN_CHUNK = 512
MAX_CHUNK = 4096
 
# Voice Activity Detection parameters
ENERGY_THRESHOLD = 300  # Adjust based on your mic and environment
SILENCE_THRESHOLD = 0.8  # Seconds of silence to consider a pause

# Initialize PyAudio
audio = pyaudio.PyAudio()

# Start microphone stream
stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                    input=True, frames_per_buffer=INITIAL_CHUNK)

# Initialize the recognizer
rec = KaldiRecognizer(model, RATE)
rec.SetWords(True)  # Enable word timestamps

print("Listening... (Ctrl+C to stop)")

# Buffer for audio
audio_buffer = b''
last_audio_time = time.time()
is_speaking = False
silence_frames = 0
current_chunk = INITIAL_CHUNK
last_result = ""
continuous_text = ""

def calculate_energy(audio_data):
    """Calculate energy of audio data"""
    # Convert byte array to numpy array
    data_np = np.frombuffer(audio_data, dtype=np.int16)
    # Calculate RMS energy
    return np.sqrt(np.mean(np.square(data_np)))

# Process the audio stream
try:
    while True:
        data = stream.read(current_chunk, exception_on_overflow=False)
        energy = calculate_energy(data)
        
        # Detect if speaking based on energy level
        is_speaking_now = energy > ENERGY_THRESHOLD
        
        # Update chunk size based on speech activity
        if is_speaking_now and not is_speaking:
            # Speech just started
            is_speaking = True
            current_chunk = MIN_CHUNK  # Use smaller chunks during speech
            silence_frames = 0
            # Clear buffer when new speech starts
            audio_buffer = b''
        elif not is_speaking_now and is_speaking:
            # Speech might be ending
            silence_frames += 1
            if silence_frames > (RATE / current_chunk * SILENCE_THRESHOLD):
                # Confirmed end of speech
                is_speaking = False
                current_chunk = MAX_CHUNK  # Use larger chunks during silence
                
                # Process remaining buffer
                if audio_buffer:
                    rec.AcceptWaveform(audio_buffer)
                    final_result = json.loads(rec.FinalResult())
                    if final_result.get("text", ""):
                        print("Text:", final_result.get("text", ""))
                    audio_buffer = b''
        
        # Add data to buffer
        audio_buffer += data
        
        # Process buffer if enough data or during silence
        if len(audio_buffer) > RATE or not is_speaking:
            if rec.AcceptWaveform(audio_buffer):
                result = json.loads(rec.Result())
                text = result.get("text", "")
                
                # Filter out duplicated content
                if text and text != last_result:
                    # Check if the new text overlaps with previous text
                    if last_result and text.startswith(last_result[-10:]):
                        # Remove the overlapping part
                        text = text[len(last_result[-10:]):]
                    
                    print("Text:", text)
                    last_result = text
                    continuous_text += " " + text
                
                audio_buffer = b''
            elif len(audio_buffer) > RATE * 2:  # Don't let buffer grow too large
                # Process part of the buffer
                rec.AcceptWaveform(audio_buffer[:RATE])
                audio_buffer = audio_buffer[RATE:]
        
        # Print partial results
        partial_result = json.loads(rec.PartialResult())
        partial_text = partial_result.get("partial", "")
        if partial_text:
            print("Partial:", partial_text, end='\r')
        
        time.sleep(0.01)  # Small delay to reduce CPU usage
        
except KeyboardInterrupt:
    # Clean up
    stream.stop_stream()
    stream.close()
    audio.terminate()
    final_result = json.loads(rec.FinalResult())
    print("\nFinal Text:", final_result.get("text", ""))
    print("\nComplete Transcript:", continuous_text)