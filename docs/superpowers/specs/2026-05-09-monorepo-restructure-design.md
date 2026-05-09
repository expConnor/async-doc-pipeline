# Monorepo Restructure Design

**Date:** 2026-05-09
**Branch:** `restructure-project-with-shared-folder-24`

## Goal

Reshape the repo so that:

1. Domain code (DTOs, interfaces, ORM, repositories, infrastructure clients, exceptions, settings, migrations) lives in a `shared/` package independent of FastAPI.
2. HTTP-layer code lives in a top-level `api/` package — flat, no nested wrappers. The previous `api/app/` and inner `api/app/api/` wrappers go away.
3. Dockerfiles live under a top-level `docker/` directory, decoupled from the package directories.
4. Poetry is hoisted to a single root `pyproject.toml` with dependency groups so each future deployable installs only what it needs.

The flatten matters for two reasons. First, with `api/` directly importable as a top-level package (alongside `shared/`), a single `PYTHONPATH=.` resolves all imports — no per-service path entries. Second, the existing `api/app/api/routes/` nesting (a directory named `api` inside a wrapper named `app` inside a deploy folder named `api`) is collapsed: routes, schemas, and middleware live directly under `api/`, so import paths match the file tree.

**Zero behavior change.** Same routes, same database, same FastAPI app, same `docker compose up` developer flow. Only file paths, import statements, and packaging change.

This is a precondition for the worker spec. The worker is **out of scope here** and will be designed and implemented in a later, separate effort. No `worker/` directory, no `worker` Poetry group, no parser code is added by this work — but the chosen layout means the future worker mirrors `api/` symmetrically (top-level package, Dockerfile under `docker/worker.Dockerfile`).

## Why

`api/app/` currently holds two kinds of code:

1. **Domain code** — DTOs, ORM models, repositories, RabbitMQ + S3 clients, exceptions, settings. None of it depends on FastAPI. ~80% of `api/app/` falls in this bucket.
2. **HTTP-layer code** — routes, request/response schemas, middleware, FastAPI app entry, API-specific DI wiring. Depends on FastAPI.

Today the worker would have to either import from `api.app.*` (transitively pulling FastAPI into the worker image) or duplicate the domain code. Neither is acceptable. Pre-extracting `shared/` removes the choice: the worker (and any future deployable) imports from `shared.*` and never touches FastAPI.

The flatten of `api/app/` → `api/` (and the collapse of the inner `api/app/api/` routing wrapper) is a complementary cleanup. It makes the API package symmetric with `shared/`: both are top-level packages with directory names that match their import paths. It also removes a long-standing nesting awkwardness (`api/app/api/routes/`) that has no semantic justification — the inner `api` was just "the routing namespace" and the outer `app` was just "everything." Folding both wrappers gives `api/routes/`, which reads exactly as it is.

## Target Layout

```
doc-pipeline/
├── pyproject.toml              # NEW: root, declares groups
├── poetry.lock                 # NEW: root, single lockfile
├── alembic.ini                 # MOVED from api/alembic.ini
├── .dockerignore               # NEW
├── docker/
│   └── api.Dockerfile          # MOVED + RENAMED from api/Dockerfile
├── shared/                     # top-level package, importable as `shared.*`
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
├── api/                        # top-level package, importable as `api.*`
│   ├── __init__.py
│   ├── routes/                 # MOVED from api/app/api/routes/
│   ├── schemas/                # MOVED from api/app/api/schemas/
│   ├── middleware.py           # MOVED from api/app/api/middleware.py
│   ├── services/               # MOVED from api/app/services/
│   ├── core/                   # MOVED from api/app/core/ (only API-only files)
│   │   ├── __init__.py
│   │   ├── container.py
│   │   ├── providers.py
│   │   ├── dependencies.py
│   │   └── security.py
│   └── app.py                  # MOVED from api/app/app.py — uvicorn entry: `api.app:app`
├── docker-compose.yml          # UPDATED: build.context, build.dockerfile, command, volumes
├── docs/
├── tmp/
├── .env / .env.example
├── mise.toml
├── .pre-commit-config.yaml
└── README.md
```

`api/app/` ceases to exist. The empty `api/tests/` directory is moved to `tests/` at the repo root (or deleted; test layout will be revisited when tests are written) — addressed in step 7 of the order of operations.

Worker preview (not added by this spec, shown only to confirm symmetry):
```
worker/                          # future top-level package, importable as `worker.*`
docker/worker.Dockerfile         # future
```

## Module Relocations

All moves are pure file moves followed by import-path updates. No code edits inside the modules themselves.

### Domain code → `shared/`

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

### HTTP-layer code → flattened `api/`

| From                                                | To                                            |
| --------------------------------------------------- | --------------------------------------------- |
| `api/app/api/routes/*`                              | `api/routes/*`                                |
| `api/app/api/schemas/*`                             | `api/schemas/*`                               |
| `api/app/api/middleware.py`                         | `api/middleware.py`                           |
| `api/app/services/*`                                | `api/services/*`                              |
| `api/app/core/container.py`                         | `api/core/container.py`                       |
| `api/app/core/providers.py`                         | `api/core/providers.py`                       |
| `api/app/core/dependencies.py`                      | `api/core/dependencies.py`                    |
| `api/app/core/security.py`                          | `api/core/security.py`                        |
| `api/app/app.py`                                    | `api/app.py`                                  |

After step 3 of the order of operations, the directory `api/app/` no longer exists. Its `__init__.py` and any `__pycache__` are removed.

### Build + packaging

| From                                                | To                                            |
| --------------------------------------------------- | --------------------------------------------- |
| `api/Dockerfile`                                    | `docker/api.Dockerfile`                       |
| `api/alembic.ini`                                   | `alembic.ini` (root)                          |
| `api/pyproject.toml`                                | `pyproject.toml` (root)                       |
| `api/poetry.lock`                                   | `poetry.lock` (root)                          |

## Root `pyproject.toml`

Single root file. Three dependency groups (`main` is implicit; `api` and `dev` are declared).

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

Both `shared/` and `api/` are top-level packages at the repo root. A single `sys.path` entry — the repo root — resolves both:

- **In the Docker image:** `WORKDIR /workspace` and `ENV PYTHONPATH=/workspace`. The API container only needs `shared/` and `api/` copied to `/workspace/`.
- **On the dev host:** running `poetry run ...` from the repo root works without any `PYTHONPATH` setup, because the working directory is implicitly on `sys.path` for normal imports. For tooling that doesn't honor cwd (some IDE configurations), an explicit `PYTHONPATH=.` is enough.

The `worker` group is intentionally absent. Adding an empty group provides no value; the worker spec will introduce it together with its dependencies.

## Dockerfile (`docker/api.Dockerfile`)

The Dockerfile moves to a top-level `docker/` directory and uses the repo root as build context, so it can copy both `shared/` and `api/`. Conceptually:

1. Base: `python:3.13-slim` (unchanged).
2. `WORKDIR /workspace`.
3. `ENV PYTHONPATH=/workspace` — single entry covers both `shared` and `api`.
4. Copy `pyproject.toml` and `poetry.lock` from the build context (root) into the workspace. This is the cache layer.
5. Install Poetry, then `poetry install --only main,api --no-root --no-interaction --no-ansi`.
6. Copy `shared/` into `/workspace/shared/`.
7. Copy `api/` into `/workspace/api/`.
8. `EXPOSE 8080`.
9. `CMD` left to docker-compose / orchestrator (matches current behavior).

A `.dockerignore` at the repo root excludes `worker/` (when added later), `tests/`, `docs/`, `tmp/`, `.git/`, `.venv/`, `__pycache__/`, and `*.pyc` from build contexts.

## `docker-compose.yml` Changes

The `api` service block changes its `build` directive from `./api` to:

```yaml
build:
  context: .
  dockerfile: docker/api.Dockerfile
```

The `command` updates from `uvicorn app.app:app ...` to `uvicorn api.app:app ...` to reflect the new package name.

Volumes for hot-reload mount the relevant source paths into the container:

```yaml
volumes:
  - ./shared:/workspace/shared
  - ./api:/workspace/api
```

Environment, ports, and healthchecks for `postgres` and `rabbitmq` are unchanged.

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

Two top-level namespaces post-refactor:

- `shared.*` — domain code that physically moved into `shared/`.
- `api.*` — HTTP-layer code, formerly under `app.*` (and partially under `app.api.*`), now flattened into `api/`.

The old `app.*` namespace disappears entirely. Every import statement currently using `app.*` rewrites to either `shared.*` or `api.*`.

### Domain → `shared.*`

| Old import prefix             | New import prefix                |
| ----------------------------- | -------------------------------- |
| `app.dtos.*`                  | `shared.dtos.*`                  |
| `app.interfaces.*`            | `shared.interfaces.*`            |
| `app.infrastructure.*`        | `shared.infrastructure.*`        |
| `app.core.exceptions`         | `shared.core.exceptions`         |
| `app.core.settings.*`         | `shared.core.settings.*`         |
| `app.core.config`             | `shared.core.config`             |

Service implementations (which remain in the API package) import their interfaces from `shared.interfaces.services.*`. Repositories and infrastructure clients import their interfaces from `shared.interfaces.repositories.*` and `shared.interfaces.infrastructure.*`.

### HTTP layer → `api.*`

| Old import prefix             | New import prefix                |
| ----------------------------- | -------------------------------- |
| `app.api.routes.*`            | `api.routes.*`                   |
| `app.api.schemas.*`           | `api.schemas.*`                  |
| `app.api.middleware`          | `api.middleware`                 |
| `app.services.*`              | `api.services.*`                 |
| `app.core.container`          | `api.core.container`             |
| `app.core.providers`          | `api.core.providers`             |
| `app.core.dependencies`       | `api.core.dependencies`          |
| `app.core.security`           | `api.core.security`              |
| `app.app`                     | `api.app`                        |

The uvicorn entry point in `docker-compose.yml` updates from `app.app:app` to `api.app:app` for the same reason.

### Where edits land

- Files moved into `shared/` already have their own internal cross-imports (e.g., `shared/infrastructure/repositories/job.py` imports from `shared/dtos/job.py`). These need rewriting per the domain table.
- Files moved into `api/` import both `shared.*` (DTOs, interfaces, exceptions, settings, infra clients) and `api.*` (other HTTP-layer modules). These need rewriting per both tables.
- `shared/migrations/env.py` updates to `from shared.core.config import get_settings` and `from shared.infrastructure.models import Base`.

## Order of Operations

Followed in this order during implementation. The repo will be temporarily un-importable between steps 2 and 4; that is by design — performing all moves first, then a single import sweep, is cleaner than interleaving.

1. **Poetry hoist.** Move `api/pyproject.toml` and `api/poetry.lock` to repo root. Add `[tool.poetry.group.api.dependencies]` (FastAPI, uvicorn) and `[tool.poetry.group.dev.dependencies]` (Ruff). Move all other production deps to `[tool.poetry.dependencies]`. Set `package-mode = false`. Run `poetry install` and diff resolved versions against the old lockfile to confirm zero drift.
2. **Create `shared/`.** Make the directory with empty `__init__.py` files at each level. Physically move modules per the "Domain code → `shared/`" relocation table. Repo no longer imports correctly — expected.
3. **Flatten `api/`.** Move `api/app/api/routes/` → `api/routes/`, `api/app/api/schemas/` → `api/schemas/`, `api/app/api/middleware.py` → `api/middleware.py`, `api/app/services/` → `api/services/`, `api/app/core/{container,providers,dependencies,security}.py` → `api/core/`, `api/app/app.py` → `api/app.py`. Add `api/__init__.py` and `api/core/__init__.py`. Delete the now-empty `api/app/` directory.
4. **Sweep imports.** Apply the full import-migration table across the entire codebase: `app.dtos.* → shared.dtos.*`, `app.interfaces.* → shared.interfaces.*`, `app.infrastructure.* → shared.infrastructure.*`, `app.core.{exceptions,settings,config} → shared.core.*`, `app.api.* → api.*`, `app.services.* → api.services.*`, `app.core.{container,providers,dependencies,security} → api.core.*`, `app.app → api.app`. Repo compiles again. `python -c "import api.app; import shared"` succeeds from the repo root.
5. **Migrations.** Move `api/alembic.ini` to repo root. Update `script_location` to `shared/migrations`. Move `api/migrations/` to `shared/migrations/`. Update `shared/migrations/env.py` imports to `from shared.core.config import get_settings` and `from shared.infrastructure.models import Base`. Grep `shared/migrations/versions/` for any `app.*` imports and rewrite. Verify `poetry run alembic upgrade head` runs cleanly against an empty test database.
6. **Dockerfile + `.dockerignore`.** Create `docker/api.Dockerfile` with the structure described above. Delete `api/Dockerfile`. Create `.dockerignore` at the repo root excluding `worker/`, `tests/`, `docs/`, `tmp/`, `.git/`, `.venv/`, `__pycache__/`, `*.pyc`.
7. **`docker-compose.yml`.** Update the `api` service: `build.context: .`, `build.dockerfile: docker/api.Dockerfile`, `command: uvicorn api.app:app --host 0.0.0.0 --port 8080 --reload`, volumes `./shared:/workspace/shared` and `./api:/workspace/api`. The empty `api/tests/` directory is also moved to `tests/` at the repo root (or deleted) for consistency.
8. **Smoke test.**
   - `docker compose up` starts cleanly.
   - `GET /health` returns 200.
   - `poetry run alembic upgrade head` applies migrations.
   - End-to-end on a clean DB: create a document, upload a PDF via the presigned URL, create a job, confirm the message lands in RabbitMQ via the management UI. (Worker still doesn't exist; the message sits in the queue — that is fine.)
9. **Lint.** Run `poetry run ruff check .` and `poetry run ruff format .` from repo root. Fix any formatting drift.

## File Impact Summary

| Category                                                | Count (approx.) | Action                                         |
| ------------------------------------------------------- | --------------- | ---------------------------------------------- |
| Python files moved into `shared/`                       | ~35             | DTOs (~5), interfaces (~13), infrastructure (~10), exceptions (1), settings (~3), config (1), migrations (~7) |
| Python files moved into flattened `api/`                | ~15             | routes (3), schemas (4), middleware (1), services (4), api-only core (4), `app.py` (1) |
| Python files with import edits (subset of those moved)  | ~50             | Every moved Python file has its `app.*` imports rewritten to `shared.*` or `api.*`. Files that contained no Python imports (`__init__.py` files) are exempt. |
| Files with structural edits                             | 4               | Root `pyproject.toml`, `docker-compose.yml`, `shared/migrations/env.py`, `alembic.ini` (`script_location`) |
| Files deleted                                           | 3               | `api/pyproject.toml`, `api/poetry.lock`, `api/Dockerfile` (replaced by root + `docker/`) |
| Files added                                             | 4               | Root `pyproject.toml`, root `poetry.lock`, root `.dockerignore`, `docker/api.Dockerfile` |
| Directories deleted                                     | 1               | `api/app/` (empty after step 3) |

## Out of Scope

To preserve focus and reviewability, the following are deliberately **not** changed by this work:

- **No worker code.** No `worker/` directory, no consumer logic, no parsers, no `worker` Poetry group.
- **No service-layer reorganization.** All four services (`AccountService`, `DocumentService`, `JobService`, `ArtifactService`) move into `api/services/` and continue to be consumed only by HTTP routes. Moving them to `shared/` is a future concern if and when the worker (or another deployable) needs them.
- **No interface or DI changes.** The DI container, providers, and `Annotated` dependencies move from `api/app/core/` to `api/core/` but their content is unchanged; only their imports update.
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
