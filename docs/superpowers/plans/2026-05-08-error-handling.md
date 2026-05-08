# Error Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace bare `ValueError` raises and missing 404s with a typed exception hierarchy, a consistent JSON error envelope, and infrastructure error wrapping across S3, RabbitMQ, and Postgres.

**Architecture:** Four layers — a typed exception hierarchy in `app/core/exceptions.py`, raise sites in services and infra clients, a `get_or_raise` helper in `app/core/errors.py`, and three exception handlers registered in `app/app.py` that produce a uniform JSON envelope for all error types.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.x async, boto3, aio_pika

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/core/exceptions.py` | Create | Typed exception hierarchy |
| `app/core/errors.py` | Create | `get_or_raise` helper |
| `app/app.py` | Modify | Register three exception handlers |
| `app/services/job.py` | Modify | Replace `ValueError` with domain exceptions |
| `app/services/artifact.py` | Modify | Inject `document_repo`, add 404 check |
| `app/core/container.py` | Modify | Pass `document_repo` to `ArtifactService` |
| `app/api/routes/jobs.py` | Modify | Remove `try/except ValueError`, use `get_or_raise` |
| `app/infrastructure/storage/s3_client.py` | Modify | Wrap `ClientError` as `StorageException` |
| `app/infrastructure/messaging/rabbitmq_client.py` | Modify | Wrap `aio_pika` errors as `QueueException` |
| `app/infrastructure/repositories/document.py` | Modify | Wrap `SQLAlchemyError` as `DatabaseException` |
| `app/infrastructure/repositories/job.py` | Modify | Wrap `SQLAlchemyError` as `DatabaseException` |
| `app/infrastructure/repositories/artifact.py` | Modify | Wrap `SQLAlchemyError` as `DatabaseException` |
| `app/infrastructure/repositories/account.py` | Modify | Wrap `SQLAlchemyError` as `DatabaseException` |

---

### Task 1: Create the exception hierarchy

**Files:**
- Create: `api/app/core/exceptions.py`

- [ ] **Step 1: Create `app/core/exceptions.py`**

```python
from __future__ import annotations

from typing import Any


class AppException(Exception):
    _status_code: int = 500
    _message: str = "An unexpected error occurred."
    _errors: dict[str, Any] = {}

    def __init__(
        self,
        status_code: int | None = None,
        message: str | None = None,
        errors: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.errors = errors

    def get_status_code(self) -> int:
        return self.status_code or self._status_code

    def get_message(self) -> str:
        return self.message or self._message

    def get_errors(self) -> dict[str, Any]:
        return self.errors or self._errors


class DocumentNotFoundException(AppException):
    _status_code = 404
    _message = "Document not found."


class DocumentNotUploadedException(AppException):
    _status_code = 409
    _message = "Document has not been uploaded."


class JobNotFoundException(AppException):
    _status_code = 404
    _message = "Job not found."


class StorageException(AppException):
    _status_code = 503
    _message = "Storage service unavailable."


class QueueException(AppException):
    _status_code = 503
    _message = "Queue service unavailable."


class DatabaseException(AppException):
    _status_code = 503
    _message = "Database service unavailable."
```

- [ ] **Step 2: Verify imports**

```bash
cd api && python -c "from app.core.exceptions import AppException, DocumentNotFoundException, JobNotFoundException, StorageException, QueueException, DatabaseException; print('ok')"
```

Expected output: `ok`

- [ ] **Step 3: Commit**

```bash
git add api/app/core/exceptions.py
git commit -m "feat: add typed exception hierarchy"
```

---

### Task 2: Create the `get_or_raise` helper

**Files:**
- Create: `api/app/core/errors.py`

- [ ] **Step 1: Create `app/core/errors.py`**

```python
from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from app.core.exceptions import AppException


async def get_or_raise(awaitable: Awaitable[Any], exception: AppException) -> Any:
    result = await awaitable
    if result is None:
        raise exception
    return result
```

- [ ] **Step 2: Verify imports**

```bash
cd api && python -c "from app.core.errors import get_or_raise; print('ok')"
```

Expected output: `ok`

- [ ] **Step 3: Commit**

```bash
git add api/app/core/errors.py
git commit -m "feat: add get_or_raise helper"
```

---

### Task 3: Register exception handlers in `app/app.py`

All three handlers produce the same JSON envelope:

```json
{
  "status": "error",
  "status_code": 404,
  "type": "DocumentNotFoundException",
  "message": "Document not found.",
  "errors": {}
}
```

**Files:**
- Modify: `api/app/app.py`

- [ ] **Step 1: Replace `app/app.py` with the handler-aware version**

```python
from app.api.middleware import LoggingMiddleware
from app.api.routes import documents, health, jobs
from app.core.exceptions import AppException
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

app = FastAPI()

app.add_middleware(LoggingMiddleware)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(jobs.router)


def _error_body(
    status_code: int, type_: str, message: str, errors: dict
) -> dict:
    return {
        "status": "error",
        "status_code": status_code,
        "type": type_,
        "message": message,
        "errors": errors,
    }


@app.exception_handler(AppException)
async def internal_exception_handler(
    request: Request, exc: AppException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.get_status_code(),
        content=_error_body(
            status_code=exc.get_status_code(),
            type_=type(exc).__name__,
            message=exc.get_message(),
            errors=exc.get_errors(),
        ),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(
            status_code=exc.status_code,
            type_="HTTPException",
            message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            errors={},
        ),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors: dict[str, list[str]] = {}
    for error in exc.errors():
        field = str(error["loc"][-1]) if error["loc"] else "body"
        msg = error.get("ctx", {}).get("reason") or error["msg"]
        errors.setdefault(field, []).append(msg.lower())
    return JSONResponse(
        status_code=422,
        content=_error_body(
            status_code=422,
            type_="RequestValidationError",
            message="Request validation failed.",
            errors=errors,
        ),
    )
```

- [ ] **Step 2: Verify the app starts**

```bash
cd api && python -c "from app.app import app; print('ok')"
```

Expected output: `ok`

- [ ] **Step 3: Commit**

```bash
git add api/app/app.py
git commit -m "feat: register exception handlers with structured error envelope"
```

---

### Task 4: Update `app/services/job.py`

Replace both `ValueError` raises with typed domain exceptions.

**Files:**
- Modify: `api/app/services/job.py`

- [ ] **Step 1: Replace `app/services/job.py`**

```python
from __future__ import annotations

from typing import Any

from app.core.exceptions import DocumentNotFoundException, DocumentNotUploadedException
from app.dtos.job import CreateJobDTO, JobDTO, JobStatus
from app.interfaces.infrastructure.messaging import IMessagingService
from app.interfaces.infrastructure.storage import IStorageService
from app.interfaces.repositories.document import IDocumentRepository
from app.interfaces.repositories.job import IJobRepository
from app.interfaces.services.job import IJobService


class JobService(IJobService):
    def __init__(
        self,
        job_repo: IJobRepository,
        document_repo: IDocumentRepository,
        messaging: IMessagingService,
        storage: IStorageService,
        queue: str,
    ) -> None:
        self._repo = job_repo
        self._document_repo = document_repo
        self._messaging = messaging
        self._storage = storage
        self._queue = queue

    async def get(
        self, session: Any, job_id: int, account_id: int
    ) -> JobDTO | None:
        return await self._repo.get_by_id(session, job_id, account_id)

    async def create(self, session: Any, dto: CreateJobDTO) -> JobDTO:
        document = await self._document_repo.get_by_id(
            session, dto.document_id, dto.account_id
        )
        if document is None:
            raise DocumentNotFoundException()
        if not await self._storage.object_exists(document.object_key):
            raise DocumentNotUploadedException()

        job = await self._repo.create(session, dto)
        await self._messaging.enqueue(
            self._queue,
            {
                "job_id": job.id,
                "document_id": job.document_id,
                "artifact_types": [t.value for t in job.artifact_types],
            },
        )
        return await self._repo.update_status(session, job.id, JobStatus.QUEUED)
```

- [ ] **Step 2: Commit**

```bash
git add api/app/services/job.py
git commit -m "feat: replace ValueError raises with DocumentNotFoundException and DocumentNotUploadedException"
```

---

### Task 5: Update `app/services/artifact.py` and `app/core/container.py`

Inject `document_repo` into `ArtifactService` so it can check document existence before listing artifacts.

**Files:**
- Modify: `api/app/services/artifact.py`
- Modify: `api/app/core/container.py`

- [ ] **Step 1: Replace `app/services/artifact.py`**

```python
from __future__ import annotations

from typing import Any

from app.core.exceptions import DocumentNotFoundException
from app.dtos.artifact import ArtifactWithUrlDTO
from app.interfaces.infrastructure.storage import IStorageService
from app.interfaces.repositories.artifact import IArtifactRepository
from app.interfaces.repositories.document import IDocumentRepository
from app.interfaces.services.artifact import IArtifactService


class ArtifactService(IArtifactService):
    def __init__(
        self,
        artifact_repo: IArtifactRepository,
        storage: IStorageService,
        document_repo: IDocumentRepository,
    ) -> None:
        self._repo = artifact_repo
        self._storage = storage
        self._document_repo = document_repo

    async def list_for_document(
        self, session: Any, document_id: int, account_id: int
    ) -> list[ArtifactWithUrlDTO]:
        document = await self._document_repo.get_by_id(
            session, document_id, account_id
        )
        if document is None:
            raise DocumentNotFoundException()
        artifacts = await self._repo.list_by_document_id(
            session, document_id, account_id
        )
        result = []
        for artifact in artifacts:
            url = await self._storage.generate_download_url(artifact.object_key)
            result.append(ArtifactWithUrlDTO(artifact=artifact, download_url=url))
        return result
```

- [ ] **Step 2: Update `artifact_service()` in `app/core/container.py`**

Find this method (line 94–98):

```python
    def artifact_service(self) -> IArtifactService:
        return ArtifactService(
            artifact_repo=self.artifact_repository(),
            storage=self.storage_service(),
        )
```

Replace with:

```python
    def artifact_service(self) -> IArtifactService:
        return ArtifactService(
            artifact_repo=self.artifact_repository(),
            storage=self.storage_service(),
            document_repo=self.document_repository(),
        )
```

- [ ] **Step 3: Commit**

```bash
git add api/app/services/artifact.py api/app/core/container.py
git commit -m "feat: add document existence check to ArtifactService.list_for_document"
```

---

### Task 6: Update `app/api/routes/jobs.py`

Remove the `try/except ValueError` block (job service no longer raises `ValueError`) and replace the inline `None` check with `get_or_raise`.

**Files:**
- Modify: `api/app/api/routes/jobs.py`

- [ ] **Step 1: Replace `app/api/routes/jobs.py`**

```python
from app.api.schemas.requests.jobs import ProcessDocumentRequest
from app.api.schemas.responses.jobs import JobResponse
from app.core.dependencies import CurrentAccount, DBSession, JobServiceDep
from app.core.errors import get_or_raise
from app.core.exceptions import JobNotFoundException
from app.dtos.job import CreateJobDTO, JobDTO
from fastapi import APIRouter

router = APIRouter()


def _to_response(job: JobDTO) -> JobResponse:
    return JobResponse(
        id=job.id,
        document_id=job.document_id,
        status=job.status,
        artifact_types=job.artifact_types,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        error_message=job.error_message,
        created_at=job.created_at,
        queued_at=job.queued_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        last_attempt_at=job.last_attempt_at,
    )


@router.post(
    "/documents/{document_id}/process",
    response_model=JobResponse,
    status_code=201,
)
async def process_document(
    document_id: int,
    body: ProcessDocumentRequest,
    account: CurrentAccount,
    session: DBSession,
    job_service: JobServiceDep,
) -> JobResponse:
    dto = CreateJobDTO(
        account_id=account.id,
        document_id=document_id,
        artifact_types=body.artifact_types,
    )
    job = await job_service.create(session, dto)
    return _to_response(job)


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    account: CurrentAccount,
    session: DBSession,
    job_service: JobServiceDep,
) -> JobResponse:
    job = await get_or_raise(
        job_service.get(session, job_id, account.id),
        JobNotFoundException(),
    )
    return _to_response(job)
```

- [ ] **Step 2: Commit**

```bash
git add api/app/api/routes/jobs.py
git commit -m "feat: remove try/except ValueError in jobs route, use get_or_raise"
```

---

### Task 7: Wrap S3 errors in `app/infrastructure/storage/s3_client.py`

**Files:**
- Modify: `api/app/infrastructure/storage/s3_client.py`

- [ ] **Step 1: Replace `app/infrastructure/storage/s3_client.py`**

```python
import asyncio

import boto3
from botocore.exceptions import ClientError

from ...core.exceptions import StorageException
from ...interfaces.infrastructure.storage import IStorageService


class S3StorageService(IStorageService):
    def __init__(self, bucket: str, region: str) -> None:
        self._bucket = bucket
        self._client = boto3.client("s3", region_name=region)

    async def generate_upload_url(self, object_key: str) -> str:
        try:
            return await asyncio.to_thread(
                self._client.generate_presigned_url,
                "put_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=3600,
            )
        except ClientError as e:
            raise StorageException() from e

    async def generate_download_url(self, object_key: str) -> str:
        try:
            return await asyncio.to_thread(
                self._client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=3600,
            )
        except ClientError as e:
            raise StorageException() from e

    async def object_exists(self, object_key: str) -> bool:
        try:
            await asyncio.to_thread(
                self._client.head_object,
                Bucket=self._bucket,
                Key=object_key,
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise StorageException() from e
```

- [ ] **Step 2: Commit**

```bash
git add api/app/infrastructure/storage/s3_client.py
git commit -m "feat: wrap S3 ClientError as StorageException"
```

---

### Task 8: Wrap RabbitMQ errors in `app/infrastructure/messaging/rabbitmq_client.py`

**Files:**
- Modify: `api/app/infrastructure/messaging/rabbitmq_client.py`

- [ ] **Step 1: Replace `app/infrastructure/messaging/rabbitmq_client.py`**

```python
import json

import aio_pika
from aio_pika.abc import AbstractRobustConnection

from ...core.exceptions import QueueException
from ...interfaces.infrastructure.messaging import IMessagingService


class RabbitMQMessagingService(IMessagingService):
    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: AbstractRobustConnection | None = None

    async def _get_connection(self) -> AbstractRobustConnection:
        if self._connection is None or self._connection.is_closed:
            self._connection = await aio_pika.connect_robust(self._url)
        return self._connection

    async def enqueue(self, queue: str, payload: dict) -> None:
        try:
            connection = await self._get_connection()
            async with connection.channel() as channel:
                await channel.declare_queue(queue, durable=True)
                await channel.default_exchange.publish(
                    aio_pika.Message(
                        body=json.dumps(payload).encode(),
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    ),
                    routing_key=queue,
                )
        except aio_pika.exceptions.AMQPError as e:
            raise QueueException() from e

    async def queue_depth(self, queue: str) -> int:
        connection = await self._get_connection()
        async with connection.channel() as channel:
            declared = await channel.declare_queue(queue, passive=True)
            return declared.declaration_result.message_count or 0
```

- [ ] **Step 2: Commit**

```bash
git add api/app/infrastructure/messaging/rabbitmq_client.py
git commit -m "feat: wrap aio_pika AMQPError as QueueException"
```

---

### Task 9: Wrap SQLAlchemy errors in all repositories

Each repository method wraps its DB calls so that SQLAlchemy errors surface as `DatabaseException` rather than a raw 500.

**Files:**
- Modify: `api/app/infrastructure/repositories/document.py`
- Modify: `api/app/infrastructure/repositories/job.py`
- Modify: `api/app/infrastructure/repositories/artifact.py`
- Modify: `api/app/infrastructure/repositories/account.py`

- [ ] **Step 1: Replace `app/infrastructure/repositories/document.py`**

```python
from datetime import datetime

from sqlalchemy import insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import DatabaseException
from ...dtos.document import CreateDocumentDTO, DocumentDTO
from ...infrastructure.models import Document
from ...interfaces.repositories.document import IDocumentRepository


class DocumentRepository(IDocumentRepository):
    async def create(
        self, session: AsyncSession, dto: CreateDocumentDTO
    ) -> DocumentDTO:
        try:
            query = (
                insert(Document)
                .values(
                    object_key=dto.object_key,
                    account_id=dto.account_id,
                    created_at=datetime.now(),
                )
                .returning(Document)
            )
            result = await session.execute(query)
            return self._to_dto(result.scalar_one())
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    async def get_by_id(
        self, session: AsyncSession, document_id: int, account_id: int
    ) -> DocumentDTO | None:
        try:
            query = select(Document).where(
                Document.id == document_id,
                Document.account_id == account_id,
            )
            if document := await session.scalar(query):
                return self._to_dto(document)
            return None
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    @staticmethod
    def _to_dto(model: Document) -> DocumentDTO:
        return DocumentDTO(
            id=model.id,
            object_key=model.object_key,
            account_id=model.account_id,
            created_at=model.created_at,
        )
```

- [ ] **Step 2: Replace `app/infrastructure/repositories/job.py`**

```python
from datetime import datetime

from sqlalchemy import insert, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import DatabaseException
from ...dtos.job import CreateJobDTO, JobDTO, JobStatus
from ...infrastructure.models import Job
from ...interfaces.repositories.job import IJobRepository

_STATUS_TIMESTAMP: dict[JobStatus, str] = {
    JobStatus.QUEUED: "queued_at",
    JobStatus.STARTED: "started_at",
    JobStatus.COMPLETED: "completed_at",
}


class JobRepository(IJobRepository):
    async def create(self, session: AsyncSession, dto: CreateJobDTO) -> JobDTO:
        try:
            query = (
                insert(Job)
                .values(
                    account_id=dto.account_id,
                    document_id=dto.document_id,
                    artifact_types=dto.artifact_types,
                    status=JobStatus.CREATED,
                    created_at=datetime.now(),
                )
                .returning(Job)
            )
            result = await session.execute(query)
            return self._to_dto(result.scalar_one())
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    async def get_by_id(
        self, session: AsyncSession, job_id: int, account_id: int
    ) -> JobDTO | None:
        try:
            query = select(Job).where(
                Job.id == job_id,
                Job.account_id == account_id,
            )
            if job := await session.scalar(query):
                return self._to_dto(job)
            return None
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    async def update_status(
        self, session: AsyncSession, job_id: int, status: JobStatus
    ) -> JobDTO:
        try:
            values: dict = {"status": status}
            if timestamp_col := _STATUS_TIMESTAMP.get(status):
                values[timestamp_col] = datetime.now()
            if status == JobStatus.STARTED:
                values["last_attempt_at"] = datetime.now()
                values["attempts"] = Job.attempts + 1

            query = (
                update(Job)
                .where(Job.id == job_id)
                .values(**values)
                .returning(Job)
            )
            result = await session.execute(query)
            return self._to_dto(result.scalar_one())
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    @staticmethod
    def _to_dto(model: Job) -> JobDTO:
        return JobDTO(
            id=model.id,
            account_id=model.account_id,
            document_id=model.document_id,
            status=model.status,
            artifact_types=model.artifact_types,
            attempts=model.attempts,
            max_attempts=model.max_attempts,
            error_message=model.error_message,
            created_at=model.created_at,
            queued_at=model.queued_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            last_attempt_at=model.last_attempt_at,
        )
```

- [ ] **Step 3: Replace `app/infrastructure/repositories/artifact.py`**

```python
from datetime import datetime

from sqlalchemy import insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import DatabaseException
from ...dtos.artifact import ArtifactDTO, CreateArtifactDTO
from ...infrastructure.models import Artifact, Document
from ...interfaces.repositories.artifact import IArtifactRepository


class ArtifactRepository(IArtifactRepository):
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
                .returning(Artifact)
            )
            result = await session.execute(query)
            return self._to_dto(result.scalar_one())
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    async def list_by_document_id(
        self, session: AsyncSession, document_id: int, account_id: int
    ) -> list[ArtifactDTO]:
        try:
            query = (
                select(Artifact)
                .join(Document, Artifact.document_id == Document.id)
                .where(
                    Artifact.document_id == document_id,
                    Document.account_id == account_id,
                )
            )
            result = await session.scalars(query)
            return [self._to_dto(a) for a in result]
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    @staticmethod
    def _to_dto(model: Artifact) -> ArtifactDTO:
        return ArtifactDTO(
            id=model.id,
            job_id=model.job_id,
            document_id=model.document_id,
            artifact_type=model.artifact_type,
            object_key=model.object_key,
            created_at=model.created_at,
        )
```

- [ ] **Step 4: Replace `app/infrastructure/repositories/account.py`**

```python
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import DatabaseException
from ...dtos.account import AccountDTO
from ...infrastructure.models import Account
from ...interfaces.repositories.account import IAccountRepository


class AccountRepository(IAccountRepository):
    async def get_by_api_key_hash(
        self, session: AsyncSession, api_key_hash: str
    ) -> AccountDTO | None:
        try:
            query = select(Account).where(Account.api_key_hash == api_key_hash)
            if account := await session.scalar(query):
                return self._to_dto(account)
            return None
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    @staticmethod
    def _to_dto(model: Account) -> AccountDTO:
        return AccountDTO(id=model.id, api_key_hash=model.api_key_hash)
```

- [ ] **Step 5: Commit**

```bash
git add api/app/infrastructure/repositories/
git commit -m "feat: wrap SQLAlchemyError as DatabaseException in all repositories"
```
