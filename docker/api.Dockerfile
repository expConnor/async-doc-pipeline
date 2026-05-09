FROM python:3.13-slim

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1
ENV POETRY_VIRTUALENVS_CREATE=false
ENV PYTHONPATH=/workspace

COPY pyproject.toml poetry.lock* ./

RUN pip install --upgrade pip \
    && pip install poetry \
    && poetry install --only main,api --no-root --no-interaction --no-ansi

COPY shared/ ./shared/
COPY api/ ./api/

EXPOSE 8080
