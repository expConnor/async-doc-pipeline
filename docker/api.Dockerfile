FROM python:3.13-slim

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1
ENV POETRY_VIRTUALENVS_CREATE=false
ENV PYTHONPATH=/workspace

COPY pyproject.toml poetry.lock* ./

RUN pip install --upgrade pip \
    && pip install poetry \
    && poetry install --only main,api --no-root --no-interaction --no-ansi

COPY alembic.ini ./
COPY shared/ ./shared/
COPY api/ ./api/

EXPOSE 8080

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8080"]
