# Records from the mic into a file. Press Ctrl + C to finish
arecord -D hw:0,0 -f cd test.wav

# Plays whatever we recorded into the speakers
aplay test.wav
