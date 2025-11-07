# You need to have piper installed in the shell. The Python one is independent
# wget https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz
echo "hola que tal" | ./piper --model ../pitxu/storage/tts_models/ca_ES-upc_pau-x_low.onnx --output-raw | aplay -r 18000 -f S16_LE -t raw
