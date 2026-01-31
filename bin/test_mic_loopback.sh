# Records 5 seconds from the default input in CD quality, and plays it back to the default output
arecord -d 5 -f cd test-mic.wav && aplay test-mic.wav && rm test-mic.wav
