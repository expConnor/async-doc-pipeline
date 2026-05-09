# doc-pipeline

Scalable, event-driven Document Intelligence Pipeline on AWS. Transforms user-uploaded PDFs into structured Markdown optimized for RAG and LLM consumption. Primary goals: async processing at scale, local inference (no third-party APIs), and observability under load.

## System Flow

```
Client → POST /documents              → creates Document, returns S3 presigned upload URL
Client → PUT <presigned_url>          → uploads PDF directly to S3 (bypasses API)
Client → POST /documents/{id}/process → creates Job, enqueues to RabbitMQ
Worker → consumes job                 → fetches PDF from S3, parses, writes Markdown to S3
Client → GET /jobs/{id}              → polls job status
Client → GET /documents/{id}/artifacts → returns presigned download URLs for output
```

## Architecture

Three layers:

- **API** — FastAPI on ECS Fargate behind an ALB. Orchestrates requests, manages DB records, generates presigned URLs, enqueues jobs, enforces backpressure.
- **Worker** — ECS Fargate. Consumes from RabbitMQ, parses PDFs locally (PyMuPDF4LLM / Marker), writes Markdown to S3, updates job/artifact records in RDS.
- **Infrastructure** — S3 (raw PDFs + Markdown), Amazon MQ (RabbitMQ), RDS PostgreSQL (lifecycle tracking), VPC + IAM.

Local dev runs the same stack via Docker Compose with local Postgres and RabbitMQ.

## Key Design Decisions

- **No external parsing APIs.** All PDF-to-Markdown conversion runs locally in containerized workers — enables unrestricted stress testing.
- **Backpressure over rate limiting.** API rejects new requests when queue depth exceeds a threshold instead of using traditional rate limiting.
- **Workers scale on queue depth.** API and workers are independently scaled on ECS Fargate.
- **Object storage holds files; DB holds metadata.** `object_key` is stored in RDS; presigned URLs are generated on demand.
- **Jobs track full lifecycle with timestamps.** Enables observability queries:
  - Queue delay: `started_at - queued_at`
  - Processing latency: `completed_at - started_at`
  - Failure rates via `attempts` / `max_attempts` / `error_message`
- **Auth via hashed API keys.** Stored in `accounts.api_key_hash`, passed as `X-API-Key` header.
- **Typed exception hierarchy.** Services and infrastructure raise domain exceptions (`DocumentNotFoundException`, `JobNotFoundException`, `StorageException`, `QueueException`, `DatabaseException`) defined in `shared/core/exceptions.py`. Three handlers in `api/app.py` convert these to a structured JSON error envelope — never bare 500s. Infrastructure errors use `raise X() from e` to preserve cause chains.
- **DB-scoped retry.** The worker re-enqueues failed jobs using the DB as the sole source of truth. On failure: if `job.attempts < job.max_attempts`, mark `QUEUED` and re-enqueue; if exhausted, mark `FAILED` (terminal). `FAILED` means permanently failed — retrying jobs cycle through `QUEUED`, never touch `FAILED`. `failed_at` is only written on terminal failure.

## Folder Structure

```
doc-pipeline/
├── api/
│   ├── app.py                      # FastAPI entry point + exception handlers
│   ├── core/                       # DI container, dependencies, security
│   ├── routes/                     # HTTP routes (documents, jobs, health)
│   ├── schemas/                    # Pydantic request/response schemas
│   └── services/                   # Business logic (job creation, backpressure, upload)
├── worker/
│   ├── main.py                     # Entry point — asyncio.run(consumer.start())
│   ├── core/
│   │   └── container.py            # DI wiring
│   ├── interfaces/
│   │   └── parser.py               # IDocumentParser abstract port
│   ├── infrastructure/
│   │   ├── messaging/
│   │   │   └── consumer.py         # RabbitMQ consume loop (aio_pika)
│   │   └── parsing/
│   │       └── pymupdf_parser.py   # PyMuPDF4LLM implementation
│   └── services/
│       └── processing_service.py   # Job pipeline: fetch → parse → upload → artifact
├── shared/
│   ├── core/
│   │   ├── exceptions.py           # Typed exception hierarchy (AppException + subclasses)
│   │   └── settings/               # BaseAppSettings (pydantic-settings)
│   ├── dtos/                       # Domain data structures (Job, Document, Artifact, Account)
│   ├── interfaces/                 # Abstract ports (repositories, storage, messaging)
│   ├── infrastructure/
│   │   ├── models.py               # SQLAlchemy ORM models
│   │   ├── repositories/           # Job, Document, Artifact, Account repos
│   │   ├── messaging/              # RabbitMQ publish client
│   │   └── storage/                # S3 client (presigned URLs + get/put object)
│   └── migrations/                 # Alembic migrations
├── docker/
│   ├── api.Dockerfile
│   └── worker.Dockerfile
├── infrastructure/                 # AWS CDK (ECS, ALB, RDS, MQ, S3, VPC, IAM)
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
├── pyproject.toml                  # Shared + api + worker dependency groups
└── docker-compose.yml              # Local dev: API + Worker + Postgres + RabbitMQ
```

## Toolchain

- Python 3.13 (mise), FastAPI + uvicorn, SQLAlchemy 2.x ORM
- Worker: aio_pika (RabbitMQ consumer), pymupdf4llm (PDF parsing)
- Poetry (`pyproject.toml` with `api` and `worker` dependency groups), Ruff (lint + format via pre-commit)
- Docker Compose (local), ECS Fargate (prod), AWS CDK (IaC)

```bash
docker compose up   # local dev
ruff check .        # lint
ruff format .       # format
```

## Working Style

Connor writes all the code. Do not suggest or write code changes unless explicitly asked.

- When asked "why" or "how", explain the concept — don't show an alternative implementation.
- If something looks wrong or there's a better direction, say so directly and briefly.
- Keep answers short by default. Go deep only when asked.
- Don't add features, abstractions, or error handling beyond what was asked about.
