FROM python:3.10-slim

WORKDIR /app

RUN pip install poetry
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --no-dev

COPY README.md ./
COPY vmtt_bot vmtt_bot
RUN poetry install --no-dev

CMD poetry run python -m main
