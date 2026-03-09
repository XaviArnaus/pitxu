alsactl --file ~/.config/asound.state store
alsactl --file ~/.config/asound.state restore

## Which sound modules are loaded
lsmod | grep '^snd'