# Records from the mic into a file. Press Ctrl + C to finish
arecord -d 5 -D hw:1,0 -f cd test.wav

# Plays whatever we recorded into the speakers
aplay test.wav

# Finally deletes the temporary sound file
#rm test.wav
