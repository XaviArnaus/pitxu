# pitxu
Chatbot project over Raspberry Pi Zero 2w


# Install

## Make sure that your system has the dependencies to compile Pillow

This is needed for the internal Pillow support, for the e-Ink display

For Debian based linux distros:
```
sudo apt install libjpeg-dev zlib1g-dev libfreetype6-dev
```

## Clone the repo and move yourself in

```
git clone git@github.com:XaviArnaus/pitxu.git
cd pitxu
```

## Install Poetry

```
curl -sSL https://install.python-poetry.org | python3 -
```

## Ininitalize the project

```
make init
```

## Create a config file

```
cp config/main.yaml.dist config/main.yaml
```

... and edit it at your test

## Create an environment variables file

```
nano .env
```

... and add there your Google Geminai key, that you got for free from https://aistudio.google.com/app/apikey like

```
API_KEY=abcdefghijkl
```


# Run

```
make run
```

# Resources

## eInk Display

### Original example code in Python
It also explains dependencies from Debian. Useful to deal with PIL. Remember to port to Poetry.
https://github.com/waveshareteam/e-Paper/blob/master/RaspberryPi_JetsonNano/python/readme_rpi_EN.txt

### Manual
https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT_Manual#Demo_code