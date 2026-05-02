FROM python:3.13-slim

WORKDIR /api

ENV PYTHONUNBUFFERED=1
ENV POETRY_VIRTUALENVS_CREATE=false

COPY pyproject.toml poetry.lock* ./

RUN pip install --upgrade pip \
    && pip install poetry \
    && poetry install --only main --no-interaction --no-ansi --no-root

COPY . .

EXPOSE 8080

