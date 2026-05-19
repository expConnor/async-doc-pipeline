FROM python:3.13-slim

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1
ENV POETRY_VIRTUALENVS_CREATE=false
ENV PYTHONPATH=/workspace

COPY pyproject.toml poetry.lock* ./

RUN pip install --upgrade pip \
    && pip install poetry \
    && poetry install --only main,worker --no-root --no-interaction --no-ansi

COPY shared/ ./shared/
COPY worker/ ./worker/

CMD ["python", "-m", "worker.main"]
