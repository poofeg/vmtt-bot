# vmtt-bot
Voice-Message-to-Text Telegram Bot based on Yandex SpeechKit.

## Run in terminal
* Install Poetry: https://python-poetry.org/docs/#installation
* Type the following:
```shell
cp example.env .env
editor .env
poetry install
poetry run vmtt-bot
```

## Run in Docker
* Install Docker: https://docs.docker.com/desktop/
* Type the following:
```shell
cp example.env .env
editor .env
docker build -t vmtt-bot .
docker run -it --rm --env-file=.env vmtt-bot
```
