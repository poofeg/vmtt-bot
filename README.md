# vmtt-bot
Voice message to text Telegram Bot based on Yandex SpeechKit.

## Run in terminal
* Install Poetry: https://python-poetry.org/docs/#installation
* Type the following:
```shell
poetry install
poetry run python -m main
```

## Run in Docker
* Install Docker: https://docs.docker.com/desktop/
* Type the following:
```shell
docker build -t vmtt-bot .
docker run -it --rm --env-file=.env vmtt-bot
```
