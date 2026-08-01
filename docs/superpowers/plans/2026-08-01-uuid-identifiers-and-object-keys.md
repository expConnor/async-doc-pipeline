# UUID Identifiers and Opaque Object Keys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace integer primary keys on `documents`, `jobs`, and `artifacts` with application-generated UUIDs, and rebuild both object-key formats around them so no user-supplied text reaches a storage address.

**Architecture:** Three Alembic migrations, each paired with the code changes it enables, applied bottom-up through the layers: shared (models, DTOs, interfaces, repositories) → API (services, routes, schemas) → worker (consumer, queue payload). Key-format changes land only after identifiers are in place. The artifact uniqueness constraint moves from `object_key` to `(document_id, artifact_type)` and `ArtifactRepository.create` becomes an upsert, so reprocessing a document corrects its output in place rather than raising `IntegrityError`.

**Tech Stack:** Python 3.13, SQLAlchemy 2.x (async), Alembic, FastAPI, Pydantic v2, pytest + pytest-asyncio + pytest-mock, Postgres 16, MinIO, RabbitMQ (aio_pika), Poetry, Ruff.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-01-uuid-identifiers-and-object-keys-design.md`. Read it before starting.
- **No new dependencies.** UUIDs use `uuid.uuid4` from the standard library. `uuid.uuid7()` does not exist in Python 3.13 and must not be introduced via a third-party package.
- **`accounts.id` stays `int`.** Do not convert it. `documents.account_id` and `jobs.account_id` remain integer foreign keys.
- **Alembic head before this work:** `29e93f1a2527`. Migration revision IDs are fixed by this plan: `a1b2c3d4e5f6` (Task 1), `b2c3d4e5f6a7` (Task 5), `c3d4e5f6a7b8` (Task 6). Chain them in that order.
- **Migrations are destructive.** Each issues an explicit `TRUNCATE` before altering types — `int` cannot be cast to `uuid`. Every migration docstring must state this. `downgrade()` is equally destructive and must say so.
- **Phase boundaries require `make nuke && make setup`** to re-provision the database and an account. `local/accounts.csv` holds the API key.
- **Run `make test` at the end of every task.** It must be green before committing.
- **Ruff runs on commit** via pre-commit. Line length and formatting are enforced automatically; do not hand-format.
- **Object key formats (final state):**
  - raw: `raw/{account_id}/{document_id}.pdf`
  - artifact: `artifacts/{account_id}/{document_id}.md`
- **Invariant to preserve:** artifact types must map to distinct file extensions. Only `ArtifactType.MARKDOWN` exists, so `.md` is hardcoded.

---

## File Structure

**Modified — shared layer**
- `shared/infrastructure/models.py` — UUID PKs and FKs, artifact constraint swap
- `shared/dtos/document.py`, `shared/dtos/job.py`, `shared/dtos/artifact.py` — UUID field types
- `shared/interfaces/repositories/{document,job,artifact}.py` — UUID signatures
- `shared/interfaces/services/{document,job,artifact}.py` — UUID signatures
- `shared/infrastructure/repositories/{document,job,artifact}.py` — UUID signatures; artifact upsert
- `shared/migrations/versions/` — three new revisions

**Modified — API layer**
- `api/services/document.py` — generates the document UUID and builds the raw key
- `api/services/{job,artifact}.py` — UUID signatures
- `api/routes/documents.py` — key construction removed, UUID path params, no request body
- `api/routes/jobs.py` — UUID path params
- `api/schemas/requests/documents.py` — deleted
- `api/schemas/responses/{documents,jobs}.py` — UUID fields, `file_name` removed

**Modified — worker layer**
- `worker/infrastructure/messaging/consumer.py` — parses `job_id` as UUID
- `worker/services/processing_service.py` — new artifact key

**Modified — tests**
- `tests/integration/repositories/` — all four suites plus `conftest.py`
- `tests/unit/api/routes/` — `test_documents.py`, `test_jobs.py`, `test_auth.py`
- `tests/unit/api/services/` — all four suites
- `tests/unit/worker/services/test_processing_service.py`
- `tests/unit/worker/infrastructure/messaging/test_consumer.py`

---

## Task 1: UUID identifiers in the shared layer

Converts the database schema and everything in `shared/` to UUIDs. Key formats are untouched — `api/routes/documents.py` keeps building `raw/{account_id}/{uuid4()}/{file_name}` — which keeps this task a pure type change.

**Files:**
- Create: `shared/migrations/versions/a1b2c3d4e5f6_uuid_primary_keys.py`
- Modify: `shared/infrastructure/models.py`
- Modify: `shared/dtos/document.py`, `shared/dtos/job.py`, `shared/dtos/artifact.py`
- Modify: `shared/interfaces/repositories/document.py`, `job.py`, `artifact.py`
- Modify: `shared/interfaces/services/document.py`, `job.py`, `artifact.py`
- Modify: `shared/infrastructure/repositories/document.py`, `job.py`, `artifact.py`
- Test: `tests/integration/repositories/test_document_repository.py`, `test_job_repository.py`, `test_artifact_repository.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `Document.id`, `Job.id`, `Artifact.id` as `uuid.UUID` with `default=uuid.uuid4`. Repository signatures `get_by_id(session, document_id: UUID, account_id: int)`, `get_by_id(session, job_id: UUID, account_id: int)`, `get_for_processing(session, job_id: UUID)`, `update_status(session, job_id: UUID, ...)`, `list_by_document_id(session, document_id: UUID, account_id: int)`. DTO fields `DocumentDTO.id: UUID`, `JobDTO.id: UUID`, `JobDTO.document_id: UUID`, `CreateJobDTO.document_id: UUID`, `ArtifactDTO.id: UUID`, `ArtifactDTO.job_id: UUID`, `ArtifactDTO.document_id: UUID`, `CreateArtifactDTO.job_id: UUID`, `CreateArtifactDTO.document_id: UUID`.

- [ ] **Step 1: Update the failing tests first**

In `tests/integration/repositories/test_document_repository.py`, add `from uuid import uuid4` at the top and change line 75:

```python
async def test_get_by_id_nonexistent(repo, db_session, account):
    dto = await repo.get_by_id(db_session, uuid4(), account.id)
```

Leave line 53 (`account_id=999999`) alone — accounts stay integers.

In `tests/integration/repositories/test_job_repository.py`, add `from uuid import uuid4` and change four call sites:

```python
# line ~67, inside test_create_nonexistent_document_raises_database_exception
                document_id=uuid4(),

# line ~88
async def test_get_by_id_nonexistent(repo, db_session, account):
    dto = await repo.get_by_id(db_session, uuid4(), account.id)

# line ~104
async def test_get_for_processing_nonexistent(repo, db_session):
    dto = await repo.get_for_processing(db_session, uuid4())

# line ~197, inside test_update_status_nonexistent_job_raises_conflict
            uuid4(),
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `poetry run pytest tests/integration/repositories -v`
Expected: FAIL — Postgres rejects a UUID value against an `integer` column with `DataError`/`ProgrammingError` (surfacing as `DatabaseException` or a raw driver error).

- [ ] **Step 3: Write the migration**

Create `shared/migrations/versions/a1b2c3d4e5f6_uuid_primary_keys.py`:

```python
"""uuid_primary_keys

DESTRUCTIVE. Postgres cannot cast integer to uuid, so no existing document,
job, or artifact rows can survive this migration. It truncates all three
tables explicitly rather than depending on being run against an empty
database. Accounts are untouched.

Revision ID: a1b2c3d4e5f6
Revises: 29e93f1a2527
Create Date: 2026-08-01

"""

from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "29e93f1a2527"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("documents", "jobs", "artifacts")


def upgrade() -> None:
    """Upgrade schema. Destroys all document, job, and artifact rows."""
    # The partial index and the foreign keys both reference columns whose
    # type is about to change; Postgres will not alter a column underneath
    # them.
    op.execute("DROP INDEX IF EXISTS one_active_job_per_document")
    op.execute(
        "ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS artifacts_job_id_fkey"
    )
    op.execute(
        "ALTER TABLE artifacts "
        "DROP CONSTRAINT IF EXISTS artifacts_document_id_fkey"
    )
    op.execute(
        "ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_document_id_fkey"
    )

    op.execute("TRUNCATE artifacts, jobs, documents CASCADE")

    # Each id is SERIAL, so the nextval() default must go before the type
    # change and the now-orphaned sequence after it.
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id DROP DEFAULT")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN id TYPE uuid "
            f"USING gen_random_uuid()"
        )
        op.execute(f"DROP SEQUENCE IF EXISTS {table}_id_seq")

    op.execute(
        "ALTER TABLE jobs ALTER COLUMN document_id TYPE uuid "
        "USING gen_random_uuid()"
    )
    op.execute(
        "ALTER TABLE artifacts ALTER COLUMN document_id TYPE uuid "
        "USING gen_random_uuid()"
    )
    op.execute(
        "ALTER TABLE artifacts ALTER COLUMN job_id TYPE uuid "
        "USING gen_random_uuid()"
    )

    op.create_foreign_key(
        "jobs_document_id_fkey", "jobs", "documents", ["document_id"], ["id"]
    )
    op.create_foreign_key(
        "artifacts_document_id_fkey",
        "artifacts",
        "documents",
        ["document_id"],
        ["id"],
    )
    op.create_foreign_key(
        "artifacts_job_id_fkey", "artifacts", "jobs", ["job_id"], ["id"]
    )

    op.execute(
        """
        CREATE UNIQUE INDEX one_active_job_per_document
        ON jobs (account_id, document_id)
        WHERE status IN (
            'QUEUED'::job_status_enum,
            'STARTED'::job_status_enum
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema. Equally destructive — uuid cannot cast to integer."""
    op.execute("DROP INDEX IF EXISTS one_active_job_per_document")
    op.execute(
        "ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS artifacts_job_id_fkey"
    )
    op.execute(
        "ALTER TABLE artifacts "
        "DROP CONSTRAINT IF EXISTS artifacts_document_id_fkey"
    )
    op.execute(
        "ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_document_id_fkey"
    )

    op.execute("TRUNCATE artifacts, jobs, documents CASCADE")

    op.execute("ALTER TABLE jobs ALTER COLUMN document_id TYPE integer USING 0")
    op.execute(
        "ALTER TABLE artifacts ALTER COLUMN document_id TYPE integer USING 0"
    )
    op.execute("ALTER TABLE artifacts ALTER COLUMN job_id TYPE integer USING 0")

    for table in _TABLES:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN id TYPE integer USING 0"
        )
        op.execute(f"CREATE SEQUENCE {table}_id_seq OWNED BY {table}.id")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN id "
            f"SET DEFAULT nextval('{table}_id_seq')"
        )

    op.create_foreign_key(
        "jobs_document_id_fkey", "jobs", "documents", ["document_id"], ["id"]
    )
    op.create_foreign_key(
        "artifacts_document_id_fkey",
        "artifacts",
        "documents",
        ["document_id"],
        ["id"],
    )
    op.create_foreign_key(
        "artifacts_job_id_fkey", "artifacts", "jobs", ["job_id"], ["id"]
    )

    op.execute(
        """
        CREATE UNIQUE INDEX one_active_job_per_document
        ON jobs (account_id, document_id)
        WHERE status IN (
            'QUEUED'::job_status_enum,
            'STARTED'::job_status_enum
        )
        """
    )
```

- [ ] **Step 4: Update the models**

In `shared/infrastructure/models.py`, add these imports alongside the existing ones:

```python
import uuid

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
```

Change the three primary keys and three foreign keys. `Account` is untouched.

```python
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    object_key: Mapped[str] = mapped_column(unique=True, nullable=False)
    file_name: Mapped[str] = mapped_column(nullable=False)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        default=func.now(), nullable=False
    )
```

```python
class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    # ... every remaining column unchanged
```

```python
class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    # ... every remaining column unchanged, including
    # object_key: Mapped[str] = mapped_column(unique=True, nullable=False)
```

`default=uuid.uuid4` is a Python-side default. The repositories use Core-style `insert(Model).values(...)`, and SQLAlchemy Core invokes column defaults for any column absent from `values()`, so no caller needs to supply an id in this task.

- [ ] **Step 5: Update the DTOs**

`shared/dtos/document.py` — add `from uuid import UUID`:

```python
@dataclass(frozen=True)
class DocumentDTO:
    id: UUID
    object_key: str
    file_name: str
    account_id: int
    created_at: datetime
```

`CreateDocumentDTO` and `DocumentWithUploadUrlDTO` are unchanged in this task.

`shared/dtos/job.py` — add `from uuid import UUID`:

```python
@dataclass(frozen=True)
class JobDTO:
    id: UUID
    account_id: int
    document_id: UUID
    # ... every remaining field unchanged


@dataclass(frozen=True)
class CreateJobDTO:
    account_id: int
    document_id: UUID
    artifact_types: list[ArtifactType]
```

`shared/dtos/artifact.py` — add `from uuid import UUID`:

```python
@dataclass(frozen=True)
class ArtifactDTO:
    id: UUID
    job_id: UUID
    document_id: UUID
    artifact_type: ArtifactType
    object_key: str
    created_at: datetime


@dataclass(frozen=True)
class CreateArtifactDTO:
    job_id: UUID
    document_id: UUID
    artifact_type: ArtifactType
    object_key: str
```

- [ ] **Step 6: Update the interfaces**

Add `from uuid import UUID` to each file and change the annotations. `account_id` stays `int` everywhere.

`shared/interfaces/repositories/document.py`:
```python
    async def get_by_id(
        self, session: Any, document_id: UUID, account_id: int
    ) -> DocumentDTO | None: ...
```

`shared/interfaces/repositories/job.py`:
```python
    async def get_by_id(
        self, session: Any, job_id: UUID, account_id: int
    ) -> JobDTO | None: ...

    async def update_status(
        self,
        session: Any,
        job_id: UUID,
        status: JobStatus,
        *,
        expected_status: JobStatus,
        error_message: str | None = None,
    ) -> JobDTO: ...

    async def get_for_processing(
        self, session: Any, job_id: UUID
    ) -> JobDTO | None: ...
```

`shared/interfaces/repositories/artifact.py`:
```python
    async def list_by_document_id(
        self, session: Any, document_id: UUID, account_id: int
    ) -> list[ArtifactDTO]: ...
```

`shared/interfaces/services/document.py`:
```python
    async def get(
        self, session: Any, document_id: UUID, account_id: int
    ) -> DocumentDTO | None: ...
```

`shared/interfaces/services/job.py`:
```python
    async def get(
        self, session: Any, job_id: UUID, account_id: int
    ) -> JobDTO | None: ...
```

`shared/interfaces/services/artifact.py`:
```python
    async def list_for_document(
        self, session: Any, document_id: UUID, account_id: int
    ) -> list[ArtifactWithUrlDTO]: ...
```

- [ ] **Step 7: Update the repository implementations**

Add `from uuid import UUID` to each and mirror the interface signatures exactly. The method bodies do not change — SQLAlchemy handles UUID binding.

`shared/infrastructure/repositories/document.py`:
```python
    async def get_by_id(
        self, session: AsyncSession, document_id: UUID, account_id: int
    ) -> DocumentDTO | None:
```

`shared/infrastructure/repositories/job.py` — `get_by_id`, `update_status`, and `get_for_processing` take `job_id: UUID`.

`shared/infrastructure/repositories/artifact.py`:
```python
    async def list_by_document_id(
        self, session: AsyncSession, document_id: UUID, account_id: int
    ) -> list[ArtifactDTO]:
```

- [ ] **Step 8: Rebuild the database and run the integration tests**

```bash
make nuke && make setup
poetry run pytest tests/integration/repositories -v
```
Expected: PASS. The migration runs as part of `make setup`.

- [ ] **Step 9: Run the full suite**

Run: `make test`
Expected: PASS. Unit tests still pass because DTOs are plain dataclasses with no runtime type enforcement, and the API/worker layers still pass integers to mocked repositories.

- [ ] **Step 10: Commit**

```bash
git add shared/ tests/integration/repositories/
git commit -m "feat: convert document, job, and artifact ids to UUIDs

Application-generated uuid4 primary keys replace integer autoincrement on
documents, jobs, and artifacts. Removes the pre-insert-id constraint that
forced object keys to carry a throwaway uuid4 nonce.

Migration is destructive: int cannot cast to uuid, so it truncates all
three tables explicitly rather than relying on an empty database.

Key formats unchanged in this commit."
```

---

## Task 2: UUID identifiers in the API layer

**Files:**
- Modify: `api/services/document.py`, `api/services/job.py`, `api/services/artifact.py`
- Modify: `api/routes/documents.py`, `api/routes/jobs.py`
- Modify: `api/schemas/responses/documents.py`, `api/schemas/responses/jobs.py`
- Test: `tests/unit/api/routes/test_documents.py`, `test_jobs.py`, `test_auth.py`
- Test: `tests/unit/api/services/test_document_service.py`, `test_job_service.py`, `test_artifact_service.py`

**Interfaces:**
- Consumes: everything Task 1 produced — UUID DTO fields and UUID repository signatures.
- Produces: route path parameters typed `UUID` on `GET /documents/{document_id}`, `GET /documents/{document_id}/artifacts`, `POST /documents/{document_id}/process`, `GET /jobs/{job_id}`. Response fields `CreateDocumentResponse.document_id: UUID`, `DocumentResponse.id: UUID`, `ArtifactResponse.id: UUID`, `JobResponse.id: UUID`, `JobResponse.document_id: UUID`.

- [ ] **Step 1: Update the route tests**

In `tests/unit/api/routes/test_documents.py`, add imports and a fixed UUID constant so assertions can reference it:

```python
from uuid import UUID

DOCUMENT_ID = UUID("018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e01")
ARTIFACT_ID = UUID("018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e02")
JOB_ID = UUID("018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e03")
MISSING_ID = UUID("018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e99")
```

Replace `id=42` in `DOCUMENT_DTO` with `id=DOCUMENT_ID`, and in the artifact DTO replace `id=7`, `job_id=10`, `document_id=42` with `id=ARTIFACT_ID`, `job_id=JOB_ID`, `document_id=DOCUMENT_ID`.

Update every URL and assertion:

```python
async def test_create_document_success_returns_201(
    client, mock_document_service
):
    mock_document_service.create.return_value = DocumentWithUploadUrlDTO(
        document=DOCUMENT_DTO,
        upload_url="https://s3.example.com/presigned",
    )

    response = await client.post(
        "/documents",
        json={"file_name": "report.pdf"},
        headers={"X-API-KEY": API_KEY},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["document_id"] == str(DOCUMENT_ID)
    assert body["upload_url"] == "https://s3.example.com/presigned"


async def test_get_document_success_returns_200(client, mock_document_service):
    mock_document_service.get.return_value = DOCUMENT_DTO

    response = await client.get(
        f"/documents/{DOCUMENT_ID}", headers={"X-API-KEY": API_KEY}
    )

    assert response.status_code == 200
```

Replace `/documents/99` with `f"/documents/{MISSING_ID}"`, `/documents/42/artifacts` with `f"/documents/{DOCUMENT_ID}/artifacts"`, and `/documents/99/artifacts` with `f"/documents/{MISSING_ID}/artifacts"`.

Add a new test for malformed UUIDs:

```python
async def test_get_document_malformed_uuid_returns_422(client):
    response = await client.get(
        "/documents/not-a-uuid", headers={"X-API-KEY": API_KEY}
    )
    assert response.status_code == 422
```

In `tests/unit/api/routes/test_jobs.py`, apply the same treatment: define `DOCUMENT_ID`, `JOB_ID`, `MISSING_ID` constants, replace `id=99`/`document_id=42` in the job DTO, and swap every `/documents/42/process`, `/documents/99/process`, `/jobs/999`, `/jobs/99` for f-string URLs built from those constants.

In `tests/unit/api/routes/test_auth.py`, replace the three `/documents/1` URLs with a valid UUID string so the tests exercise authentication rather than path validation:

```python
DOCUMENT_URL = "/documents/018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e01"
```

- [ ] **Step 2: Update the service tests**

In `tests/unit/api/services/test_document_service.py`, `test_job_service.py`, and `test_artifact_service.py`, add `from uuid import uuid4` and replace every integer `id=`, `document_id=`, and `job_id=` value with `uuid4()` or a module-level constant. Leave `account_id=1` as an integer.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `poetry run pytest tests/unit/api -v`
Expected: FAIL — routes still declare `document_id: int`, so a UUID in the path returns 422 and the assertions on `str(DOCUMENT_ID)` do not match.

- [ ] **Step 4: Update the response schemas**

`api/schemas/responses/documents.py` — add `from uuid import UUID`:

```python
class CreateDocumentResponse(BaseModel):
    document_id: UUID
    upload_url: str


class DocumentResponse(BaseModel):
    id: UUID
    file_name: str
    created_at: datetime


class ArtifactResponse(BaseModel):
    id: UUID
    artifact_type: ArtifactType
    download_url: str
```

`api/schemas/responses/jobs.py` — add `from uuid import UUID`:

```python
class JobResponse(BaseModel):
    id: UUID
    document_id: UUID
    # ... every remaining field unchanged
```

Pydantic serialises `UUID` to its canonical string form in JSON automatically.

- [ ] **Step 5: Update the routes**

`api/routes/documents.py` — add `from uuid import UUID` and change both path parameters:

```python
async def get_document(
    document_id: UUID,
    ...
```
```python
async def list_artifacts(
    document_id: UUID,
    ...
```

`api/routes/jobs.py` — add `from uuid import UUID`:

```python
async def process_document(
    document_id: UUID,
    ...
```
```python
async def get_job(
    job_id: UUID,
    ...
```

- [ ] **Step 6: Update the API services**

Add `from uuid import UUID` to each and mirror the interface signatures from Task 1.

`api/services/document.py`:
```python
    async def get(
        self, session: Any, document_id: UUID, account_id: int
    ) -> DocumentDTO | None:
```

`api/services/job.py`:
```python
    async def get(
        self, session: Any, job_id: UUID, account_id: int
    ) -> JobDTO | None:
```

`api/services/artifact.py`:
```python
    async def list_for_document(
        self, session: Any, document_id: UUID, account_id: int
    ) -> list[ArtifactWithUrlDTO]:
```

`JobService.create` publishes `job.id` to RabbitMQ. Change the payload so the UUID is JSON-serialisable:

```python
        await self._messaging.enqueue(
            self._queue,
            {
                "job_id": str(job.id),
                "document_id": str(job.document_id),
                "artifact_types": [t.value for t in job.artifact_types],
            },
        )
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `poetry run pytest tests/unit/api -v`
Expected: PASS

- [ ] **Step 8: Run the full suite**

Run: `make test`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add api/ tests/unit/api/
git commit -m "feat: accept and return UUIDs across the API layer

Route path parameters, response schemas, and service signatures all move to
UUID. The RabbitMQ payload serialises job_id and document_id as strings so
the message stays JSON-encodable.

Adds coverage for malformed UUIDs returning 422."
```

---

## Task 3: UUID identifiers in the worker

**Files:**
- Modify: `worker/infrastructure/messaging/consumer.py`
- Test: `tests/unit/worker/infrastructure/messaging/test_consumer.py`
- Test: `tests/unit/worker/services/test_processing_service.py`

**Interfaces:**
- Consumes: the queue payload from Task 2 (`job_id` and `document_id` as strings) and the UUID repository signatures from Task 1.
- Produces: `RabbitMQConsumer._handle` parses `job_id` into a `uuid.UUID` before touching the repositories; `_handle_failure(job_id: UUID, ...)` re-enqueues it as a string.

- [ ] **Step 1: Write the failing test**

Add `from uuid import UUID, uuid4` to the imports of `tests/unit/worker/infrastructure/messaging/test_consumer.py`, then add these two tests. The file already provides a `msg` fixture (an `AsyncMock` whose `.body` you set directly) and `consumer`, `job_repo`, `queued_job_dto`, `started_job_dto` fixtures — use those.

```python
async def test_handle_parses_job_id_as_uuid(consumer, msg, job_repo):
    job_id = uuid4()
    msg.body = f'{{"job_id": "{job_id}"}}'.encode()
    job_repo.get_for_processing.return_value = None

    await consumer._handle(msg)

    passed_id = job_repo.get_for_processing.await_args.args[1]
    assert passed_id == job_id
    assert isinstance(passed_id, UUID)


async def test_handle_malformed_uuid_acks_and_drops(consumer, msg, job_repo):
    msg.body = b'{"job_id": "not-a-uuid"}'

    await consumer._handle(msg)

    job_repo.get_for_processing.assert_not_called()
    msg.ack.assert_called_once()
```

`get_for_processing` is called as `get_for_processing(session, job_id)`, so `await_args.args[1]` is the id.

Then update every existing test in the file that sets a payload: replace `msg.body = b'{"job_id": 10}'` with a module-level constant so the id is a valid UUID string.

```python
JOB_ID = UUID("018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e03")
DOCUMENT_ID = UUID("018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e01")
JOB_BODY = f'{{"job_id": "{JOB_ID}"}}'.encode()
```

Replace `id=10` and `document_id=1` in `queued_job_dto` and `started_job_dto` with `id=JOB_ID` and `document_id=DOCUMENT_ID`.

`test_handle_null_job_id_acks` needs no change — `UUID(str(None))` raises `ValueError`, which the widened `except` clause in Step 3 catches, so the message is still acked and dropped.

In `tests/unit/worker/services/test_processing_service.py`, replace `id=10` / `document_id=1` in `job_dto` and `id=1` in `document_dto` with matching module-level UUID constants. `job_dto.document_id` **must equal** `document_dto.id`, or the artifact-key tests in Task 7 will compare against the wrong value. Replace the bare `10` in `processing_service.process(session, 10)` calls with the job constant.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `poetry run pytest tests/unit/worker -v`
Expected: FAIL — `_handle` passes the raw string through, so `passed_id` is `str`, not `UUID`; the malformed case reaches the repository instead of being dropped.

- [ ] **Step 3: Parse the job id as a UUID in the consumer**

In `worker/infrastructure/messaging/consumer.py`, add `from uuid import UUID` and change the payload-parsing block in `_handle`:

```python
        try:
            payload = json.loads(msg.body)
            job_id = UUID(str(payload["job_id"]))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning("consumer.poison_message_dropped")
            await msg.ack()
            return
```

`ValueError` joins the caught exceptions because `UUID(...)` raises it for a malformed string. A message whose `job_id` is not a valid UUID is structurally broken and cannot be fixed by redelivery, so it is acked and dropped like any other poison message.

Change the `_handle_failure` signature and its re-enqueue payload:

```python
    async def _handle_failure(
        self,
        job_id: UUID,
        attempts: int,
        max_attempts: int,
        exc: Exception,
    ) -> None:
```
```python
                    await self._messaging.enqueue(
                        self._queue, {"job_id": str(job_id)}
                    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `poetry run pytest tests/unit/worker -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `make test`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add worker/ tests/unit/worker/
git commit -m "feat: parse job_id as UUID in the worker consumer

The queue payload now carries job_id as a string. The consumer parses it
into a UUID before reaching the repositories, and treats an unparseable
value as a poison message: acked and dropped, since redelivery cannot fix
a structurally broken id.

Re-enqueue on retry serialises the UUID back to a string."
```

---

## Task 4: Raw object key derives from the document UUID

Moves UUID generation and key construction out of the route and into `DocumentService`, and switches the raw key to `raw/{account_id}/{document_id}.pdf`. `file_name` still exists as a column and request field — it is simply no longer part of the key.

**Files:**
- Modify: `api/services/document.py`
- Modify: `api/routes/documents.py`
- Modify: `shared/dtos/document.py` (`CreateDocumentDTO` gains `id`)
- Modify: `shared/infrastructure/repositories/document.py` (`create` writes the supplied id)
- Test: `tests/unit/api/services/test_document_service.py`
- Test: `tests/unit/api/routes/test_documents.py`

**Interfaces:**
- Consumes: `DocumentDTO.id: UUID` and the repository signatures from Task 1.
- Produces: `CreateDocumentDTO(id: UUID, object_key: str, file_name: str, account_id: int)`. `DocumentService.create(session, dto)` unchanged in signature but now the *route* passes `file_name` and `account_id` only via a new service-level entry point: `DocumentService.create(session, account_id: int, file_name: str) -> DocumentWithUploadUrlDTO`.

- [ ] **Step 1: Write the failing test**

In `tests/unit/api/services/test_document_service.py`, add these imports and a module-level helper:

```python
import re
from uuid import UUID

RAW_KEY_PATTERN = re.compile(
    r"^raw/(\d+)/"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.pdf$"
)


def _echo_created(captured):
    """Return a repo.create side_effect that records and echoes the DTO."""

    async def _side_effect(_session, dto):
        captured["dto"] = dto
        return DocumentDTO(
            id=dto.id,
            object_key=dto.object_key,
            file_name=dto.file_name,
            account_id=dto.account_id,
            created_at=datetime(2026, 1, 1),
        )

    return _side_effect
```

The file already provides `session`, `document_service`, `document_repo`, `storage`, and `document_dto` fixtures (from `tests/unit/api/services/conftest.py`). Add these two tests:

```python
async def test_create_builds_key_from_account_and_document_id(
    session, document_service, document_repo, storage
):
    captured = {}
    document_repo.create.side_effect = _echo_created(captured)
    storage.generate_upload_url.return_value = "https://s3/presigned"

    result = await document_service.create(
        session, account_id=1, file_name="a b#c.pdf"
    )

    dto = captured["dto"]
    match = RAW_KEY_PATTERN.match(dto.object_key)
    assert match is not None, f"unexpected key: {dto.object_key}"
    assert match.group(1) == "1"
    assert UUID(match.group(2)) == dto.id
    assert result.document.id == dto.id


async def test_create_key_contains_no_file_name(
    session, document_service, document_repo, storage
):
    captured = {}
    document_repo.create.side_effect = _echo_created(captured)
    storage.generate_upload_url.return_value = "https://s3/presigned"

    await document_service.create(
        session, account_id=1, file_name="secret-name.pdf"
    )

    assert "secret-name" not in captured["dto"].object_key
```

The `a b#c.pdf` filename is chosen deliberately: a space and a `#` are exactly the characters that produced the `403 SignatureDoesNotMatch` when filenames were part of the key.

Then update the two existing tests, which currently build a `CreateDocumentDTO` themselves and pass it to `create`. They must call the new signature instead:

```python
async def test_create_returns_document_with_upload_url(
    session, document_service, document_repo, storage, document_dto
):
    document_repo.create.return_value = document_dto
    storage.generate_upload_url.return_value = (
        "https://s3.example.com/presigned"
    )

    result = await document_service.create(
        session, account_id=1, file_name="test.pdf"
    )

    assert result.document == document_dto
    assert result.upload_url == "https://s3.example.com/presigned"
    storage.generate_upload_url.assert_called_once_with(document_dto.object_key)


async def test_create_propagates_storage_exception(
    session, document_service, document_repo, storage, document_dto
):
    document_repo.create.return_value = document_dto
    storage.generate_upload_url.side_effect = StorageException()

    with pytest.raises(StorageException):
        await document_service.create(
            session, account_id=1, file_name="test.pdf"
        )
```

The `CreateDocumentDTO` import becomes unused in this file — remove it.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `poetry run pytest tests/unit/api/services/test_document_service.py -v`
Expected: FAIL with `TypeError` — `DocumentService.create` currently takes `(session, dto)`, not `(session, account_id, file_name)`.

- [ ] **Step 3: Add `id` to `CreateDocumentDTO`**

`shared/dtos/document.py`:

```python
@dataclass(frozen=True)
class CreateDocumentDTO:
    id: UUID
    object_key: str
    file_name: str
    account_id: int
```

- [ ] **Step 4: Write the supplied id in the repository**

`shared/infrastructure/repositories/document.py`:

```python
            query = (
                insert(Document)
                .values(
                    id=dto.id,
                    object_key=dto.object_key,
                    file_name=dto.file_name,
                    account_id=dto.account_id,
                    created_at=datetime.now(),
                )
                .returning(Document)
            )
```

The `default=uuid.uuid4` on the model stays — it now only fires for insert paths that do not supply an id, such as test fixtures.

- [ ] **Step 5: Move generation and key construction into the service**

`api/services/document.py`:

```python
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from shared.dtos.document import (
    CreateDocumentDTO,
    DocumentDTO,
    DocumentWithUploadUrlDTO,
)
from shared.interfaces.infrastructure.storage import IStorageService
from shared.interfaces.repositories.document import IDocumentRepository
from shared.interfaces.services.document import IDocumentService


class DocumentService(IDocumentService):
    def __init__(
        self,
        document_repo: IDocumentRepository,
        storage: IStorageService,
    ) -> None:
        self._repo = document_repo
        self._storage = storage

    async def create(
        self, session: Any, account_id: int, file_name: str
    ) -> DocumentWithUploadUrlDTO:
        document_id = uuid4()
        dto = CreateDocumentDTO(
            id=document_id,
            object_key=self._raw_key(account_id, document_id),
            file_name=file_name,
            account_id=account_id,
        )
        document = await self._repo.create(session, dto)
        upload_url = await self._storage.generate_upload_url(
            document.object_key
        )
        return DocumentWithUploadUrlDTO(
            document=document, upload_url=upload_url
        )

    async def get(
        self, session: Any, document_id: UUID, account_id: int
    ) -> DocumentDTO | None:
        return await self._repo.get_by_id(session, document_id, account_id)

    @staticmethod
    def _raw_key(account_id: int, document_id: UUID) -> str:
        return f"raw/{account_id}/{document_id}.pdf"
```

Update `shared/interfaces/services/document.py` to match:

```python
    @abstractmethod
    async def create(
        self, session: Any, account_id: int, file_name: str
    ) -> DocumentWithUploadUrlDTO: ...
```

- [ ] **Step 6: Simplify the route**

`api/routes/documents.py` — remove the `uuid4` import and the key construction:

```python
@router.post(
    "/documents", response_model=CreateDocumentResponse, status_code=201
)
async def create_document(
    body: CreateDocumentRequest,
    account: CurrentAccount,
    session: DBSession,
    document_service: DocumentServiceDep,
) -> CreateDocumentResponse:
    result = await document_service.create(
        session, account_id=account.id, file_name=body.file_name
    )
    structlog.contextvars.bind_contextvars(document_id=result.document.id)
    return CreateDocumentResponse(
        document_id=result.document.id,
        upload_url=result.upload_url,
    )
```

Also delete the now-unused `CreateDocumentDTO` import from the route.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `poetry run pytest tests/unit/api -v`
Expected: PASS

- [ ] **Step 8: Rebuild and run the full suite**

```bash
make nuke && make setup
make test
```
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add api/ shared/ tests/unit/api/
git commit -m "feat: derive raw object key from the document UUID

Raw keys become raw/{account_id}/{document_id}.pdf. The throwaway uuid4
nonce is gone — the document's own id now provides uniqueness.

UUID generation and key construction move from the route into
DocumentService: a storage key format is a storage concern, and the service
must own generation anyway since the id has to exist before the insert."
```

---

## Task 5: Drop `file_name`

**Files:**
- Create: `shared/migrations/versions/b2c3d4e5f6a7_drop_documents_file_name.py`
- Delete: `api/schemas/requests/documents.py`
- Modify: `shared/infrastructure/models.py`, `shared/dtos/document.py`
- Modify: `shared/infrastructure/repositories/document.py`
- Modify: `api/services/document.py`, `api/routes/documents.py`
- Modify: `api/schemas/responses/documents.py`
- Modify: `worker/services/processing_service.py`
- Test: `tests/integration/repositories/conftest.py`, `test_document_repository.py`
- Test: `tests/unit/api/routes/test_documents.py`, `tests/unit/api/services/test_document_service.py`
- Test: `tests/unit/worker/services/test_processing_service.py`

**Interfaces:**
- Consumes: `DocumentService.create(session, account_id, file_name)` from Task 4.
- Produces: `DocumentService.create(session, account_id: int) -> DocumentWithUploadUrlDTO`. `CreateDocumentDTO(id: UUID, object_key: str, account_id: int)`. `DocumentDTO` without `file_name`. `POST /documents` accepts no request body.

- [ ] **Step 1: Write the failing test**

In `tests/unit/api/routes/test_documents.py`, replace `test_create_document_missing_file_name_returns_422` with:

```python
async def test_create_document_no_body_returns_201(
    client, mock_document_service
):
    mock_document_service.create.return_value = DocumentWithUploadUrlDTO(
        document=DOCUMENT_DTO,
        upload_url="https://s3.example.com/presigned",
    )

    response = await client.post("/documents", headers={"X-API-KEY": API_KEY})

    assert response.status_code == 201
    body = response.json()
    assert body["document_id"] == str(DOCUMENT_ID)


async def test_get_document_response_has_no_file_name(
    client, mock_document_service
):
    mock_document_service.get.return_value = DOCUMENT_DTO

    response = await client.get(
        f"/documents/{DOCUMENT_ID}", headers={"X-API-KEY": API_KEY}
    )

    assert response.status_code == 200
    assert "file_name" not in response.json()
```

Remove `file_name=` from the `DOCUMENT_DTO` constructor and drop the `json={"file_name": ...}` argument from the remaining create test.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `poetry run pytest tests/unit/api/routes/test_documents.py -v`
Expected: FAIL — `DocumentDTO` still requires `file_name`, and `POST /documents` still requires a body.

- [ ] **Step 3: Write the migration**

Create `shared/migrations/versions/b2c3d4e5f6a7_drop_documents_file_name.py`:

```python
"""drop_documents_file_name

DESTRUCTIVE. Drops documents.file_name. The column held an unverified
client-supplied label that the API could never validate, since uploads go
directly to S3 and the API never sees the file. Its values are not
recoverable by downgrade.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Destroys all stored file names."""
    op.drop_column("documents", "file_name")


def downgrade() -> None:
    """Downgrade schema. Recreates the column empty — values are lost."""
    op.add_column(
        "documents",
        sa.Column(
            "file_name", sa.String(), nullable=False, server_default=""
        ),
    )
    op.alter_column("documents", "file_name", server_default=None)
```

- [ ] **Step 4: Remove `file_name` from the model and DTOs**

In `shared/infrastructure/models.py`, delete the `file_name` line from `Document`.

In `shared/dtos/document.py`:

```python
@dataclass(frozen=True)
class DocumentDTO:
    id: UUID
    object_key: str
    account_id: int
    created_at: datetime


@dataclass(frozen=True)
class CreateDocumentDTO:
    id: UUID
    object_key: str
    account_id: int
```

- [ ] **Step 5: Remove it from the repository**

`shared/infrastructure/repositories/document.py` — drop `file_name=dto.file_name` from the `insert(...).values(...)` call and `file_name=model.file_name` from `_to_dto`.

- [ ] **Step 6: Remove it from the service, route, and schemas**

`api/services/document.py`:

```python
    async def create(
        self, session: Any, account_id: int
    ) -> DocumentWithUploadUrlDTO:
        document_id = uuid4()
        dto = CreateDocumentDTO(
            id=document_id,
            object_key=self._raw_key(account_id, document_id),
            account_id=account_id,
        )
        document = await self._repo.create(session, dto)
        upload_url = await self._storage.generate_upload_url(
            document.object_key
        )
        return DocumentWithUploadUrlDTO(
            document=document, upload_url=upload_url
        )
```

`shared/interfaces/services/document.py`:

```python
    @abstractmethod
    async def create(
        self, session: Any, account_id: int
    ) -> DocumentWithUploadUrlDTO: ...
```

Delete `api/schemas/requests/documents.py`.

`api/routes/documents.py` — remove the `CreateDocumentRequest` import and the `body` parameter:

```python
@router.post(
    "/documents", response_model=CreateDocumentResponse, status_code=201
)
async def create_document(
    account: CurrentAccount,
    session: DBSession,
    document_service: DocumentServiceDep,
) -> CreateDocumentResponse:
    result = await document_service.create(session, account_id=account.id)
    structlog.contextvars.bind_contextvars(document_id=result.document.id)
    return CreateDocumentResponse(
        document_id=result.document.id,
        upload_url=result.upload_url,
    )
```

`api/schemas/responses/documents.py` — remove `file_name` from `DocumentResponse`:

```python
class DocumentResponse(BaseModel):
    id: UUID
    created_at: datetime
```

`api/routes/documents.py` — remove `file_name=document.file_name` from the `DocumentResponse(...)` construction in `get_document`.

- [ ] **Step 7: Remove the last worker reference**

`worker/services/processing_service.py` still builds its key with `Path(document.file_name).stem`. Change it to use the job id, keeping the current structure — Task 7 replaces this line entirely:

```python
        key = f"artifacts/{job_id}/markdown.md"
```

Remove the now-unused `from pathlib import Path` import.

- [ ] **Step 8: Update the test fixtures**

In `tests/integration/repositories/conftest.py`, remove `file_name="test.pdf",` from the `document` fixture.

In `tests/integration/repositories/test_document_repository.py`, remove `file_name=` from every `CreateDocumentDTO(...)` and drop any assertion on it.

In `tests/unit/api/services/test_document_service.py`:

- Remove `file_name="test.pdf",` from the `document_dto` fixture.
- Remove `file_name=dto.file_name,` from the `_echo_created` helper added in Task 4.
- Drop the `file_name=` argument from all four `document_service.create(...)` calls, leaving `document_service.create(session, account_id=1)`.
- In `test_create_key_contains_no_file_name`, there is no longer a filename to pass. Replace that test with one asserting the key holds only the two ids:

```python
async def test_create_key_contains_only_account_and_document_ids(
    session, document_service, document_repo, storage
):
    captured = {}
    document_repo.create.side_effect = _echo_created(captured)
    storage.generate_upload_url.return_value = "https://s3/presigned"

    await document_service.create(session, account_id=1)

    dto = captured["dto"]
    assert dto.object_key == f"raw/1/{dto.id}.pdf"
```

In `tests/unit/worker/services/test_processing_service.py`, remove `file_name="report.pdf",` from the `document_dto` fixture.

- [ ] **Step 9: Rebuild and run the full suite**

```bash
make nuke && make setup
make test
```
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat: drop file_name from documents

file_name was an unverified client assertion: uploads go straight to S3, so
the API never sees the file and cannot check the name describes it. With it
out of both object keys it was load-bearing for nothing but a display field
on a system with no UI.

Removing it eliminates the encoding, validation, and header-injection
surface entirely rather than managing it. POST /documents now takes no body."
```

---

## Task 6: Artifact uniqueness constraint and upsert

**Files:**
- Create: `shared/migrations/versions/c3d4e5f6a7b8_artifact_unique_document_type.py`
- Modify: `shared/infrastructure/models.py`
- Modify: `shared/infrastructure/repositories/artifact.py`
- Test: `tests/integration/repositories/test_artifact_repository.py`

**Interfaces:**
- Consumes: UUID DTOs from Task 1.
- Produces: `ArtifactRepository.create` upserts on `(document_id, artifact_type)`, returning the inserted-or-updated `ArtifactDTO`. `Artifact.object_key` is no longer unique.

- [ ] **Step 1: Write the failing test**

In `tests/integration/repositories/test_artifact_repository.py`, replace `test_create_duplicate_object_key_raises_database_exception` — the constraint it asserts is being removed — with:

```python
async def test_create_same_document_and_type_upserts(
    repo, db_session, account, document, job, artifact
):
    """Reprocessing overwrites the artifact row rather than raising."""
    result = await repo.create(
        db_session,
        CreateArtifactDTO(
            job_id=job.id,
            document_id=document.id,
            artifact_type=ArtifactType.MARKDOWN,
            object_key="artifacts/1/test.md",
        ),
    )

    assert result.id == artifact.id
    assert result.object_key == "artifacts/1/test.md"

    rows = await repo.list_by_document_id(db_session, document.id, account.id)
    assert len(rows) == 1


async def test_create_upsert_refreshes_job_id(
    db_session, repo, account, document, job, artifact
):
    """The surviving row points at the run that most recently produced it."""
    second_job = await db_session.execute(
        insert(Job)
        .values(
            account_id=account.id,
            document_id=document.id,
            status=JobStatus.COMPLETED,
            artifact_types=[ArtifactType.MARKDOWN],
            attempts=1,
            max_attempts=3,
            created_at=datetime.now(),
            queued_at=datetime.now(),
        )
        .returning(Job)
    )
    second_job = second_job.scalar_one()

    result = await repo.create(
        db_session,
        CreateArtifactDTO(
            job_id=second_job.id,
            document_id=document.id,
            artifact_type=ArtifactType.MARKDOWN,
            object_key="artifacts/1/test.md",
        ),
    )

    assert result.id == artifact.id
    assert result.job_id == second_job.id
```

Add the imports these need at the top of the file:

```python
from datetime import datetime

from sqlalchemy import insert

from shared.dtos.job import JobStatus
from shared.infrastructure.models import Job
```

The second job uses `status=JobStatus.COMPLETED` deliberately: the `one_active_job_per_document` partial index forbids two jobs for one document in `QUEUED` or `STARTED`, so a second *active* job cannot exist. Reprocessing is only reachable once the first job has left an active status.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `poetry run pytest tests/integration/repositories/test_artifact_repository.py -v`
Expected: FAIL — `create` is a plain `INSERT` and `object_key` is still unique, so both new tests raise `DatabaseException`.

- [ ] **Step 3: Write the migration**

Create `shared/migrations/versions/c3d4e5f6a7b8_artifact_unique_document_type.py`:

```python
"""artifact_unique_document_type

Moves artifact uniqueness from object_key to (document_id, artifact_type).
The key is derived from exactly those two fields, so a separate constraint
on object_key would encode one rule twice.

DESTRUCTIVE. Existing artifact rows are truncated: pre-existing keys are
job-scoped, so more than one row can share a (document_id, artifact_type)
pair and the new constraint would fail to build.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-01

"""

from typing import Sequence, Union

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Destroys all artifact rows."""
    op.execute("TRUNCATE artifacts")
    op.execute(
        "ALTER TABLE artifacts "
        "DROP CONSTRAINT IF EXISTS artifacts_object_key_key"
    )
    op.create_unique_constraint(
        "artifacts_document_id_artifact_type_key",
        "artifacts",
        ["document_id", "artifact_type"],
    )


def downgrade() -> None:
    """Downgrade schema. Destroys all artifact rows."""
    op.execute("TRUNCATE artifacts")
    op.drop_constraint(
        "artifacts_document_id_artifact_type_key",
        "artifacts",
        type_="unique",
    )
    op.create_unique_constraint(
        "artifacts_object_key_key", "artifacts", ["object_key"]
    )
```

- [ ] **Step 4: Update the model**

In `shared/infrastructure/models.py`, add `UniqueConstraint` to the `sqlalchemy` import, drop `unique=True` from `Artifact.object_key`, and add a table argument:

```python
class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "artifact_type",
            name="artifacts_document_id_artifact_type_key",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    artifact_type: Mapped[ArtifactType] = mapped_column(
        SQLEnum(ArtifactType, name="artifact_type_enum"),
        nullable=False,
    )
    object_key: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=func.now(), nullable=False
    )
```

- [ ] **Step 5: Make `create` an upsert**

`shared/infrastructure/repositories/artifact.py` — swap the `sqlalchemy` insert import for the Postgres dialect version, which is what carries `on_conflict_do_update`:

```python
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
```

```python
    async def create(
        self, session: AsyncSession, dto: CreateArtifactDTO
    ) -> ArtifactDTO:
        try:
            query = (
                insert(Artifact)
                .values(
                    job_id=dto.job_id,
                    document_id=dto.document_id,
                    artifact_type=dto.artifact_type,
                    object_key=dto.object_key,
                    created_at=datetime.now(),
                )
                .on_conflict_do_update(
                    constraint="artifacts_document_id_artifact_type_key",
                    set_={
                        "job_id": dto.job_id,
                        "object_key": dto.object_key,
                    },
                )
                .returning(Artifact)
            )
            result = await session.execute(query)
            return self._to_dto(result.scalar_one())
        except SQLAlchemyError as e:
            raise DatabaseException() from e
```

`created_at` is deliberately not in `set_`: it records when the artifact first appeared, and refreshing it on every reprocess would lose that.

The `id` is omitted from `values()`, so the model's `default=uuid.uuid4` supplies one on insert; on conflict the existing row keeps its id, which is what the tests assert.

- [ ] **Step 6: Rebuild and run the tests**

```bash
make nuke && make setup
poetry run pytest tests/integration/repositories/test_artifact_repository.py -v
```
Expected: PASS

- [ ] **Step 7: Run the full suite**

Run: `make test`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add shared/ tests/integration/repositories/
git commit -m "feat: upsert artifacts on (document_id, artifact_type)

Generated Markdown is derived data, so a document's output has one correct
address and reprocessing should correct it in place. Uniqueness moves off
object_key, which is derived from exactly these two fields and would
otherwise encode the same rule twice.

Without this, keying artifacts by document_id would make the second
processing run violate the old unique(object_key) and raise IntegrityError."
```

---

## Task 7: Artifact object key derives from the document UUID

**Files:**
- Modify: `worker/services/processing_service.py`
- Test: `tests/unit/worker/services/test_processing_service.py`

**Interfaces:**
- Consumes: the upsert from Task 6, `JobDTO.account_id: int`, `JobDTO.document_id: UUID`.
- Produces: artifact keys of the form `artifacts/{account_id}/{document_id}.md`.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/worker/services/test_processing_service.py`. The file provides `session`, `processing_service`, `job_repo`, `document_repo`, `artifact_repo`, `storage`, `parser`, `job_dto`, and `document_dto` fixtures, and Task 3 already gave `job_dto.document_id` and `document_dto.id` matching UUID values.

```python
async def test_artifact_key_derives_from_account_and_document(
    session,
    processing_service,
    job_repo,
    document_repo,
    storage,
    parser,
    job_dto,
    document_dto,
):
    job_repo.get_for_processing.return_value = job_dto
    document_repo.get_by_id.return_value = document_dto
    storage.get_object.return_value = b"%PDF-1.4"
    parser.parse.return_value = "# Heading"

    await processing_service.process(session, job_dto.id)

    key = storage.put_object.call_args.args[0]
    assert key == f"artifacts/{job_dto.account_id}/{document_dto.id}.md"


async def test_artifact_key_omits_job_id(
    session,
    processing_service,
    job_repo,
    document_repo,
    storage,
    parser,
    job_dto,
    document_dto,
):
    job_repo.get_for_processing.return_value = job_dto
    document_repo.get_by_id.return_value = document_dto
    storage.get_object.return_value = b"%PDF-1.4"
    parser.parse.return_value = "# Heading"

    await processing_service.process(session, job_dto.id)

    assert str(job_dto.id) not in storage.put_object.call_args.args[0]


async def test_reprocessing_targets_the_same_key(
    session,
    processing_service,
    job_repo,
    document_repo,
    storage,
    parser,
    job_dto,
    document_dto,
):
    """Two runs of the same document must address one object, so the
    repository upsert lands on the row it is meant to replace."""
    import dataclasses
    from uuid import uuid4

    document_repo.get_by_id.return_value = document_dto
    storage.get_object.return_value = b"%PDF-1.4"
    parser.parse.return_value = "# Heading"

    job_repo.get_for_processing.return_value = job_dto
    await processing_service.process(session, job_dto.id)
    first_key = storage.put_object.call_args.args[0]

    second_job = dataclasses.replace(job_dto, id=uuid4())
    job_repo.get_for_processing.return_value = second_job
    await processing_service.process(session, second_job.id)
    second_key = storage.put_object.call_args.args[0]

    assert first_key == second_key
```

The third test is the unit-level half of the upsert story: it proves two different jobs for one document compute an identical key, which is the precondition for the integration-level upsert in Task 6 to overwrite rather than duplicate.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `poetry run pytest tests/unit/worker/services/test_processing_service.py -v`
Expected: FAIL — the key is still `artifacts/{job_id}/markdown.md`.

- [ ] **Step 3: Change the key**

In `worker/services/processing_service.py`, replace the key construction:

```python
        key = f"artifacts/{job.account_id}/{document.id}.md"
```

`account_id` comes from the job, which the method already loaded — `artifacts` has no `account_id` column of its own and does not gain one.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `poetry run pytest tests/unit/worker/services/test_processing_service.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `make test`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add worker/ tests/unit/worker/
git commit -m "feat: derive artifact key from account and document ids

Artifact keys become artifacts/{account_id}/{document_id}.md, mirroring the
raw layout. Adds the account prefix that was missing entirely, so artifacts
are tenant-partitioned and can be scoped by IAM policy or lifecycle rule.

job_id leaves the path: nobody asks for 'the Markdown from job 7'. It was
there for uniqueness, not meaning. The .md extension carries the artifact
type, which holds while types map to distinct extensions."
```

---

## Task 8: End-to-end verification and documentation

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: everything.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Rebuild the stack**

```bash
make nuke && make setup
cat local/accounts.csv
```
Expected: a fresh account and API key.

- [ ] **Step 2: Run the full end-to-end flow**

Replace `$KEY` with the API key from `local/accounts.csv`.

```bash
# 1. Create a document — no request body
curl -s -X POST http://localhost:8080/documents \
  -H "X-API-Key: $KEY" | tee /tmp/doc.json

# 2. Upload a PDF to the presigned URL.
#    Do NOT send a Content-Type header: it is not part of what was signed.
UPLOAD_URL=$(python -c "import json;print(json.load(open('/tmp/doc.json'))['upload_url'])")
curl -s -X PUT "$UPLOAD_URL" --data-binary @path/to/test.pdf

# 3. Enqueue processing
DOC_ID=$(python -c "import json;print(json.load(open('/tmp/doc.json'))['document_id'])")
curl -s -X POST "http://localhost:8080/documents/$DOC_ID/process" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d '{}' \
  | tee /tmp/job.json

# 4. Poll until COMPLETED
JOB_ID=$(python -c "import json;print(json.load(open('/tmp/job.json'))['id'])")
curl -s "http://localhost:8080/jobs/$JOB_ID" -H "X-API-Key: $KEY"

# 5. Fetch the artifact download URL
curl -s "http://localhost:8080/documents/$DOC_ID/artifacts" -H "X-API-Key: $KEY"
```

Verify: `document_id` and `id` are UUID strings, the job reaches `COMPLETED`, and the artifact download URL returns Markdown.

- [ ] **Step 3: Verify the key formats in MinIO**

Open http://localhost:9001 (`minioadmin` / `minioadmin`) and confirm exactly two objects:

```
raw/1/<document-uuid>.pdf
artifacts/1/<document-uuid>.md
```

Neither may contain a filename or a job id.

- [ ] **Step 4: Verify the upsert against real infrastructure**

```bash
curl -s -X POST "http://localhost:8080/documents/$DOC_ID/process" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d '{}'
```

Wait for the second job to complete, then:

```bash
docker compose exec postgres psql -U postgres -d doc-pipeline-db \
  -c "SELECT id, job_id, document_id, object_key FROM artifacts;"
```

Expected: exactly **one** row, with an unchanged `id` and `object_key`, and `job_id` now pointing at the second job. MinIO must still show a single `artifacts/1/<document-uuid>.md`.

- [ ] **Step 5: Update the documentation**

In `README.md`, update the Request Flow section: `POST /documents` takes no body and returns a UUID `document_id`; note the two key formats. In the Design Decisions section, add a short entry on application-generated UUIDs and opaque keys.

In `CLAUDE.md`, update the Key design decisions list: replace the `object_key` bullet with one describing the two formats and the fact that keys carry no user-supplied text, and add a bullet on UUID identifiers being generated application-side to solve the pre-insert-id problem.

- [ ] **Step 6: Final full-suite run**

Run: `make test`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: describe UUID identifiers and opaque object keys

Records the two key formats, the no-body POST /documents contract, and why
identifiers are generated application-side."
```

---

## Verification Checklist

- [ ] `make test` green
- [ ] `poetry run ruff check .` clean
- [ ] Migration chain applies from empty: `make nuke && make setup` succeeds
- [ ] `raw/{account_id}/{document_id}.pdf` and `artifacts/{account_id}/{document_id}.md` confirmed in MinIO
- [ ] No object key contains a filename, a job id, or a `uuid4` nonce
- [ ] Reprocessing a document leaves exactly one artifact row and one artifact object
- [ ] `GET /documents/{id}` returns no `file_name`
- [ ] `POST /documents` succeeds with no request body
- [ ] A malformed UUID in any path returns 422
- [ ] `accounts.id` is still an integer
