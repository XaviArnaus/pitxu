# pitxu
Chatbot project over Raspberry Pi Zero 2w


# Install

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