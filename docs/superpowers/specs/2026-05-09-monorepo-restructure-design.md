# Monorepo Restructure Design

**Date:** 2026-05-09
**Branch:** `restructure-project-with-shared-folder-24`

## Goal

Reshape the repo so that domain code (DTOs, ORM, repositories, infrastructure clients, exceptions, settings, migrations) lives in a `shared/` package independent of FastAPI, and `api/` retains only HTTP-layer code. Hoist Poetry to a single root `pyproject.toml` with dependency groups so each future deployable installs only what it needs.

**Zero behavior change.** Same routes, same database, same FastAPI app, same `docker compose up` developer flow. Only file paths, import statements, and packaging change.

This is a precondition for the worker spec. The worker is **out of scope here** and will be designed and implemented in a later, separate effort. No `worker/` directory, no `worker` Poetry group, no parser code is added by this work.

## Why

`api/app/` currently holds two kinds of code:

1. **Domain code** — DTOs, ORM models, repositories, RabbitMQ + S3 clients, exceptions, settings. None of it depends on FastAPI. ~80% of `api/app/` falls in this bucket.
2. **HTTP-layer code** — routes, request/response schemas, middleware, FastAPI app entry, API-specific DI wiring. Depends on FastAPI.

Today the worker would have to either import from `api.app.*` (transitively pulling FastAPI into the worker image) or duplicate the domain code. Neither is acceptable. Pre-extracting `shared/` removes the choice: the worker (and any future deployable) imports from `shared.*` and never touches FastAPI.

## Target Layout

```
doc-pipeline/
├── pyproject.toml              # NEW: root, declares packages + groups
├── poetry.lock                 # NEW: root, single lockfile
├── alembic.ini                 # MOVED from api/alembic.ini
├── shared/
│   ├── __init__.py
│   ├── dtos/                   # MOVED from api/app/dtos/
│   ├── interfaces/             # MOVED from api/app/interfaces/
│   │   ├── __init__.py
│   │   ├── repositories/
│   │   ├── services/
│   │   └── infrastructure/
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── models.py           # MOVED
│   │   ├── repositories/       # MOVED
│   │   ├── messaging/          # MOVED
│   │   └── storage/            # MOVED
│   ├── core/
│   │   ├── __init__.py
│   │   ├── exceptions.py       # MOVED from api/app/core/
│   │   ├── settings/           # MOVED from api/app/core/settings/
│   │   └── config.py           # MOVED from api/app/core/config.py
│   └── migrations/             # MOVED from api/migrations/
│       ├── env.py              # imports updated
│       ├── README
│       ├── script.py.mako
│       └── versions/
├── api/
│   ├── Dockerfile              # UPDATED: build context = repo root
│   └── app/
│       ├── __init__.py
│       ├── api/                # routes, schemas, middleware (content unchanged)
│       ├── services/           # content unchanged (HTTP-only consumers for now)
│       ├── core/               # API-only DI (content unchanged)
│       │   ├── container.py
│       │   ├── providers.py
│       │   ├── dependencies.py
│       │   └── security.py
│       └── app.py              # content unchanged
├── docker-compose.yml          # UPDATED: build context, volume mounts
├── docs/
├── tmp/
├── .env / .env.example
├── mise.toml
├── .pre-commit-config.yaml
└── README.md
```

The empty `api/tests/` directory stays where it is — test layout will be addressed when tests are written, which is post-MVP per the project's deferred-tests preference.

## Module Relocations

All moves are pure file moves followed by import-path updates. No code edits inside the modules themselves.

| From                                                | To                                            |
| --------------------------------------------------- | --------------------------------------------- |
| `api/app/dtos/*`                                    | `shared/dtos/*`                               |
| `api/app/interfaces/*`                              | `shared/interfaces/*`                         |
| `api/app/infrastructure/models.py`                  | `shared/infrastructure/models.py`             |
| `api/app/infrastructure/repositories/*`             | `shared/infrastructure/repositories/*`        |
| `api/app/infrastructure/messaging/*`                | `shared/infrastructure/messaging/*`           |
| `api/app/infrastructure/storage/*`                  | `shared/infrastructure/storage/*`             |
| `api/app/core/exceptions.py`                        | `shared/core/exceptions.py`                   |
| `api/app/core/settings/*`                           | `shared/core/settings/*`                      |
| `api/app/core/config.py`                            | `shared/core/config.py`                       |
| `api/migrations/`                                   | `shared/migrations/`                          |
| `api/alembic.ini`                                   | `alembic.ini` (root)                          |
| `api/pyproject.toml`                                | `pyproject.toml` (root)                       |
| `api/poetry.lock`                                   | `poetry.lock` (root)                          |

Modules that **stay in `api/app/`** (HTTP-only, no relocation):

| Path                                                | Notes                                          |
| --------------------------------------------------- | ---------------------------------------------- |
| `api/app/app.py`                                    | FastAPI app + exception handlers              |
| `api/app/api/`                                      | Routes, schemas, middleware                   |
| `api/app/services/`                                 | Currently HTTP-only consumers                 |
| `api/app/core/container.py`                         | API DI container                              |
| `api/app/core/providers.py`                         | FastAPI `Depends`-compatible providers        |
| `api/app/core/dependencies.py`                      | Annotated type aliases for routes             |
| `api/app/core/security.py`                          | `X-API-Key` extraction                        |

## Root `pyproject.toml`

Single root file. Two declared packages, three dependency groups (`main` is implicit).

```toml
[tool.poetry]
name = "doc-pipeline"
version = "0.1.0"
description = ""
authors = ["Connor R. <connorrisse@proton.me>"]
package-mode = false

[tool.poetry.dependencies]
python = "^3.13"
sqlalchemy = ">=2.0.49,<3.0.0"
asyncpg = ">=0.31.0,<0.32.0"
aio-pika = ">=9.6.2,<10.0.0"
boto3 = ">=1.43.5,<2.0.0"
pydantic-settings = ">=2.14.0,<3.0.0"
alembic = ">=1.18.4,<2.0.0"
greenlet = ">=3.5.0,<4.0.0"

[tool.poetry.group.api.dependencies]
fastapi = ">=0.136.1,<0.137.0"
uvicorn = ">=0.46.0,<0.47.0"

[tool.poetry.group.dev.dependencies]
ruff = "*"
```

**Package mode:** `package-mode = false` (Poetry 2.x). This is an application repo, not a library — there is no need to install the project itself as a package. `poetry install --only main,api` installs the declared dependencies and nothing else; the source code is found at runtime via the import search path.

Two top-level packages must be importable: `shared` (from `shared/`) and `app` (from `api/app/`). This requires both the repo root and `api/` to be on `sys.path`.

- **In the Docker image:** `WORKDIR /workspace` and `ENV PYTHONPATH=/workspace:/workspace/api` make both resolvable. Set explicitly in the Dockerfile.
- **On the dev host:** export `PYTHONPATH=.:./api` in the shell (or via direnv / a `.envrc` / a project-local `make` target) before running `poetry run alembic ...` or `poetry run python -m ...`. The `docker compose up` flow is unaffected because the container has its own `PYTHONPATH`.

The `worker` group is intentionally absent. Adding an empty group provides no value; the worker spec will introduce it together with its dependencies.

## Dockerfile Changes (`api/Dockerfile`)

The Dockerfile moves to use the repo root as build context, so it can copy both `shared/` and `api/`. Conceptually:

1. Base: `python:3.13-slim` (unchanged).
2. `WORKDIR /workspace`.
3. `ENV PYTHONPATH=/workspace:/workspace/api` so `shared.*` and `app.*` (from `api/app/`) both resolve as top-level imports.
4. Copy `pyproject.toml` and `poetry.lock` from the build context (root) into the workspace. This is the cache layer.
5. Install Poetry, then `poetry install --only main,api --no-root --no-interaction --no-ansi`.
6. Copy `shared/` into `/workspace/shared/`.
7. Copy `api/` into `/workspace/api/`.
8. `EXPOSE 8080`.
9. `CMD` left to docker-compose / orchestrator (matches current behavior).

The image excludes `worker/` (doesn't exist), `tests/`, `docs/`, and `tmp/` — either via `.dockerignore` or by not copying them. A `.dockerignore` at the repo root is the cleanest approach.

## `docker-compose.yml` Changes

The `api` service block changes its `build` directive from `./api` to:

```yaml
build:
  context: .
  dockerfile: api/Dockerfile
```

Volumes for hot-reload mount the relevant source paths into the container:

```yaml
volumes:
  - ./shared:/workspace/shared
  - ./api:/workspace/api
```

The `command`, environment, ports, and healthchecks for `postgres` and `rabbitmq` are unchanged.

## Migration Relocation

| File                                  | Action                                                    |
| ------------------------------------- | --------------------------------------------------------- |
| `api/alembic.ini`                     | Move to repo root.                                        |
| `api/alembic.ini` `script_location`   | Update to `shared/migrations`.                            |
| `api/migrations/`                     | Move directory to `shared/migrations/`.                   |
| `shared/migrations/env.py`            | Update imports: `from shared.core.config import get_settings`, `from shared.infrastructure.models import Base`. |
| `shared/migrations/versions/*.py`     | If any version file imports from `app.*`, update; otherwise leave. |

Run from repo root: `poetry run alembic upgrade head`.

## Import Migration

Two namespaces post-refactor:

- `shared.*` — every module that physically moved into `shared/`.
- `app.*` — what's left in `api/app/`. Existing import style is preserved for HTTP code.

Mechanical replacements across the codebase:

| Old import prefix             | New import prefix                |
| ----------------------------- | -------------------------------- |
| `app.dtos.*`                  | `shared.dtos.*`                  |
| `app.infrastructure.*`        | `shared.infrastructure.*`        |
| `app.core.exceptions`         | `shared.core.exceptions`         |
| `app.core.settings.*`         | `shared.core.settings.*`         |
| `app.core.config`             | `shared.core.config`             |
| `app.interfaces.*`            | `shared.interfaces.*`            |

Interfaces are domain ports — not HTTP-specific — and move to `shared/interfaces/` alongside the repos and infra clients they describe. Service implementations remaining in `api/app/services/` import their interfaces from `shared.interfaces.services.*`.

| Old import prefix                          | New import prefix |
| ------------------------------------------ | ----------------- |
| `app.api.*`                                | unchanged         |
| `app.services.*`                           | unchanged         |
| `app.core.container / providers / dependencies / security` | unchanged |
| `app.app`                                  | unchanged         |

`app.core.config` movement is bidirectional in effect: `app.core.dependencies` (still in `api/app/`) and `app.core.container` (still in `api/app/`) currently import `from app.core.config import get_settings` — these now become `from shared.core.config import get_settings`.

## Order of Operations

Followed in this order during implementation. Each step leaves the repo in a runnable or compilable state where reasonable; steps 2–3 break the build temporarily by design.

1. Hoist `pyproject.toml` and `poetry.lock` from `api/` to repo root. Add the `[tool.poetry.group.api.dependencies]` and `[tool.poetry.group.dev.dependencies]` groups. Move all production deps to `[tool.poetry.dependencies]` except FastAPI/uvicorn (api group) and Ruff (dev group). Run `poetry install` and confirm dependencies resolve to the same versions as before.
2. Create `shared/` with empty `__init__.py` files at each level. Physically move modules per the relocation table. Repo will not import correctly at this point — that is expected.
3. Sweep imports across `api/app/` and `shared/` per the import-migration table. Repo compiles again.
4. Move `api/alembic.ini` to repo root. Update `script_location`. Move `api/migrations/` to `shared/migrations/`. Update `env.py` imports. Verify `poetry run alembic upgrade head` runs cleanly against an empty test database.
5. Rewrite `api/Dockerfile` to use root as build context, install only the `api` group, and copy `shared/` + `api/`. Add a `.dockerignore` at the repo root.
6. Update `docker-compose.yml` `api` service: `build.context: .`, `build.dockerfile: api/Dockerfile`, volume mounts to `./shared:/workspace/shared` and `./api:/workspace/api`.
7. Smoke test:
   - `docker compose up` starts cleanly.
   - `GET /health` returns 200.
   - `poetry run alembic upgrade head` (run on the host or in the container) applies migrations.
   - End-to-end: create a document, presigned-upload a PDF, create a job, observe it land in RabbitMQ. (Worker still doesn't exist; the message will sit in the queue, which is fine.)
8. Run `poetry run ruff check .` and `poetry run ruff format .` from repo root. Fix any formatting drift.

## File Impact Summary

| Category                          | Count (approx.) | Action                                         |
| --------------------------------- | --------------- | ---------------------------------------------- |
| Files moved (no code change)      | ~35             | Pure relocation: DTOs (~5), interfaces (~13), infrastructure (~10), exceptions (1), settings (~3), config (1), migrations (~3+versions) |
| Files with import-only edits      | ~25             | Mechanical `app.* → shared.*` rewrites: services (4), routes (3), middleware, `api/app/core/*` (4), `app.py`, plus the moved files' internal cross-imports |
| Files with structural edits       | 4               | Root `pyproject.toml`, `api/Dockerfile`, `docker-compose.yml`, `shared/migrations/env.py` |
| Files deleted                     | 2               | `api/pyproject.toml`, `api/poetry.lock` (replaced by root) |
| Files added                       | 3               | Root `pyproject.toml`, root `poetry.lock`, root `.dockerignore` |

## Out of Scope

To preserve focus and reviewability, the following are deliberately **not** changed by this work:

- **No worker code.** No `worker/` directory, no consumer logic, no parsers, no `worker` Poetry group.
- **No service-layer reorganization.** All four services (`AccountService`, `DocumentService`, `JobService`, `ArtifactService`) stay in `api/app/services/`. They are currently consumed only by HTTP routes; moving them to `shared/` is a future concern if and when the worker (or another deployable) needs them.
- **No interface or DI changes.** The DI container, providers, and `Annotated` dependencies in `api/app/core/` keep their shape; only their imports update.
- **No new tests.** Test layout will be designed when tests are introduced.
- **No CI/CD changes.** No GitHub Actions workflows are touched.
- **No IaC (CDK) changes.** The CDK stack is not yet implemented; this restructure is upstream of it.
- **No behavior change of any endpoint.** Identical request/response shapes, identical error envelopes, identical DB schema, identical RabbitMQ payloads.

## Risks and Mitigations

| Risk                                                              | Mitigation                                                                          |
| ----------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Dependency version drift after lockfile regeneration              | Run `poetry install` and diff resolved versions against the old `api/poetry.lock` before committing. |
| Alembic loses track of revision history due to path changes       | Move `versions/` directory wholesale; do not rename version files; the Alembic version table is keyed by revision IDs, not paths. |
| Docker build cache miss because of context change                 | Order COPY of `pyproject.toml` + `poetry.lock` before COPY of source so the install layer caches.   |
| Local dev hot-reload breaks because of new mount paths            | Verify mounts in the smoke test step; uvicorn `--reload` watches `WORKDIR` recursively. |
| Hidden import of `app.dtos.*` etc. in version migration files     | grep `versions/` for `app.` and rewrite if present.                                |
