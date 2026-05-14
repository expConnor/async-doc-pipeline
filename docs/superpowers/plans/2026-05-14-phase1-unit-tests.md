# Phase 1 Unit Tests: API + Infrastructure Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a complete unit test suite for `AccountService`, `DocumentService`, `JobService`, `ArtifactService`, and `RabbitMQMessagingService` with all interface dependencies mocked.

**Architecture:** One test file per service mirroring the source layout under `tests/unit/`. Shared fixtures live in `conftest.py` files at the appropriate directory level. `RabbitMQMessagingService` uses direct `_connection` injection rather than patching `connect_robust` for all but the three `_get_connection` tests.

**Tech Stack:** pytest, pytest-asyncio (`asyncio_mode="auto"`), pytest-mock

---

## Task 1: Configure Test Toolchain

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add test deps and pytest config to `pyproject.toml`**

Replace the `[tool.poetry.group.dev.dependencies]` section and add `[tool.pytest.ini_options]`:

```toml
[tool.poetry.group.dev.dependencies]
ruff = "*"
pytest = ">=8.0.0,<9.0.0"
pytest-asyncio = ">=0.24.0,<1.0.0"
pytest-mock = ">=3.14.0,<4.0.0"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Install new deps**

```bash
poetry install
```

Expected: resolves and installs pytest, pytest-asyncio, pytest-mock with no errors.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml poetry.lock
git commit -m "chore: add pytest, pytest-asyncio, pytest-mock to dev deps"
```

---

## Task 2: Bootstrap Directory Structure and Shared Fixtures

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/conftest.py`
- Create: `tests/unit/api/__init__.py`
- Create: `tests/unit/api/services/__init__.py`
- Create: `tests/unit/api/services/conftest.py`
- Create: `tests/unit/shared/__init__.py`
- Create: `tests/unit/shared/infrastructure/__init__.py`
- Create: `tests/unit/shared/infrastructure/messaging/__init__.py`

- [ ] **Step 1: Create all `__init__.py` files**

```bash
mkdir -p tests/unit/api/services
mkdir -p tests/unit/shared/infrastructure/messaging
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/unit/api/__init__.py
touch tests/unit/api/services/__init__.py
touch tests/unit/shared/__init__.py
touch tests/unit/shared/infrastructure/__init__.py
touch tests/unit/shared/infrastructure/messaging/__init__.py
```

- [ ] **Step 2: Create `tests/unit/conftest.py`**

```python
import pytest


@pytest.fixture
def session(mocker):
    return mocker.AsyncMock()
```

- [ ] **Step 3: Create `tests/unit/api/services/conftest.py`**

```python
import pytest

from api.services.account import AccountService
from api.services.artifact import ArtifactService
from api.services.document import DocumentService
from api.services.job import JobService


@pytest.fixture
def account_repo(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def document_repo(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def job_repo(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def artifact_repo(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def storage(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def messaging(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def account_service(account_repo):
    return AccountService(account_repo)


@pytest.fixture
def document_service(document_repo, storage):
    return DocumentService(document_repo, storage)


@pytest.fixture
def job_service(job_repo, document_repo, messaging, storage):
    return JobService(
        job_repo,
        document_repo,
        messaging,
        storage,
        queue="jobs",
        backpressure_threshold=10,
    )


@pytest.fixture
def artifact_service(artifact_repo, storage, document_repo):
    return ArtifactService(artifact_repo, storage, document_repo)
```

- [ ] **Step 4: Verify pytest can collect (zero tests, no errors)**

```bash
poetry run pytest tests/unit/ --collect-only
```

Expected: `no tests ran` with exit code 5 (or 0), no import errors.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: bootstrap unit test directory structure and shared fixtures"
```

---

## Task 3: AccountService Tests

**Files:**
- Create: `tests/unit/api/services/test_account_service.py`

- [ ] **Step 1: Create `tests/unit/api/services/test_account_service.py`**

```python
import hashlib

from shared.dtos.account import AccountDTO


async def test_authenticate_returns_dto_and_hashes_key(
    session, account_service, account_repo
):
    expected = AccountDTO(id=1, api_key_hash=None)
    account_repo.get_by_api_key_hash.return_value = expected

    result = await account_service.authenticate(session, "my-secret-key")

    expected_hash = hashlib.sha256("my-secret-key".encode()).hexdigest()
    account_repo.get_by_api_key_hash.assert_called_once_with(session, expected_hash)
    assert result == expected


async def test_authenticate_returns_none_when_no_match(
    session, account_service, account_repo
):
    account_repo.get_by_api_key_hash.return_value = None

    result = await account_service.authenticate(session, "wrong-key")

    assert result is None
```

- [ ] **Step 2: Run and verify both tests pass**

```bash
poetry run pytest tests/unit/api/services/test_account_service.py -v
```

Expected:
```
test_authenticate_returns_dto_and_hashes_key PASSED
test_authenticate_returns_none_when_no_match PASSED
2 passed
```

- [ ] **Step 3: Commit**

```bash
git add tests/unit/api/services/test_account_service.py
git commit -m "test: add AccountService unit tests"
```

---

## Task 4: DocumentService Tests

**Files:**
- Create: `tests/unit/api/services/test_document_service.py`

- [ ] **Step 1: Create `tests/unit/api/services/test_document_service.py`**

```python
from datetime import datetime

import pytest

from shared.core.exceptions import StorageException
from shared.dtos.document import CreateDocumentDTO, DocumentDTO


@pytest.fixture
def document_dto():
    return DocumentDTO(
        id=1,
        object_key="uploads/1.pdf",
        file_name="test.pdf",
        account_id=1,
        created_at=datetime(2026, 1, 1),
    )


async def test_create_returns_document_with_upload_url(
    session, document_service, document_repo, storage, document_dto
):
    document_repo.create.return_value = document_dto
    storage.generate_upload_url.return_value = "https://s3.example.com/presigned"
    dto = CreateDocumentDTO(
        object_key="uploads/1.pdf", file_name="test.pdf", account_id=1
    )

    result = await document_service.create(session, dto)

    assert result.document == document_dto
    assert result.upload_url == "https://s3.example.com/presigned"
    storage.generate_upload_url.assert_called_once_with(document_dto.object_key)


async def test_create_propagates_storage_exception(
    session, document_service, document_repo, storage, document_dto
):
    document_repo.create.return_value = document_dto
    storage.generate_upload_url.side_effect = StorageException()
    dto = CreateDocumentDTO(
        object_key="uploads/1.pdf", file_name="test.pdf", account_id=1
    )

    with pytest.raises(StorageException):
        await document_service.create(session, dto)


async def test_get_returns_dto(
    session, document_service, document_repo, document_dto
):
    document_repo.get_by_id.return_value = document_dto

    result = await document_service.get(session, document_id=1, account_id=1)

    assert result == document_dto


async def test_get_returns_none_when_not_found(
    session, document_service, document_repo
):
    document_repo.get_by_id.return_value = None

    result = await document_service.get(session, document_id=99, account_id=1)

    assert result is None
```

- [ ] **Step 2: Run and verify all four tests pass**

```bash
poetry run pytest tests/unit/api/services/test_document_service.py -v
```

Expected:
```
test_create_returns_document_with_upload_url PASSED
test_create_propagates_storage_exception PASSED
test_get_returns_dto PASSED
test_get_returns_none_when_not_found PASSED
4 passed
```

- [ ] **Step 3: Commit**

```bash
git add tests/unit/api/services/test_document_service.py
git commit -m "test: add DocumentService unit tests"
```

---

## Task 5: JobService Tests

**Files:**
- Create: `tests/unit/api/services/test_job_service.py`

- [ ] **Step 1: Create `tests/unit/api/services/test_job_service.py`**

```python
from datetime import datetime

import pytest

from shared.core.exceptions import (
    BackpressureException,
    DocumentNotFoundException,
    DocumentNotUploadedException,
    QueueException,
    StorageException,
)
from shared.dtos.artifact import ArtifactType
from shared.dtos.document import DocumentDTO
from shared.dtos.job import CreateJobDTO, JobDTO, JobStatus


@pytest.fixture
def document_dto():
    return DocumentDTO(
        id=1,
        object_key="uploads/1.pdf",
        file_name="test.pdf",
        account_id=1,
        created_at=datetime(2026, 1, 1),
    )


@pytest.fixture
def job_dto():
    return JobDTO(
        id=10,
        account_id=1,
        document_id=1,
        status=JobStatus.QUEUED,
        artifact_types=[ArtifactType.MARKDOWN],
        attempts=0,
        max_attempts=3,
        error_message=None,
        created_at=datetime(2026, 1, 1),
        queued_at=datetime(2026, 1, 1),
        started_at=None,
        completed_at=None,
        last_attempt_at=None,
        failed_at=None,
    )


@pytest.fixture
def create_dto():
    return CreateJobDTO(
        account_id=1,
        document_id=1,
        artifact_types=[ArtifactType.MARKDOWN],
    )


async def test_create_raises_when_document_not_found(
    session, job_service, document_repo, create_dto
):
    document_repo.get_by_id.return_value = None

    with pytest.raises(DocumentNotFoundException):
        await job_service.create(session, create_dto)


async def test_create_raises_when_document_not_uploaded(
    session, job_service, document_repo, storage, document_dto, create_dto
):
    document_repo.get_by_id.return_value = document_dto
    storage.object_exists.return_value = False

    with pytest.raises(DocumentNotUploadedException):
        await job_service.create(session, create_dto)


async def test_create_propagates_storage_exception_on_exists_check(
    session, job_service, document_repo, storage, document_dto, create_dto
):
    document_repo.get_by_id.return_value = document_dto
    storage.object_exists.side_effect = StorageException()

    with pytest.raises(StorageException):
        await job_service.create(session, create_dto)


async def test_create_raises_backpressure_when_depth_at_threshold(
    session, job_service, document_repo, storage, messaging, document_dto, create_dto
):
    document_repo.get_by_id.return_value = document_dto
    storage.object_exists.return_value = True
    messaging.queue_depth.return_value = 10  # == backpressure_threshold

    with pytest.raises(BackpressureException):
        await job_service.create(session, create_dto)


async def test_create_raises_backpressure_when_depth_above_threshold(
    session, job_service, document_repo, storage, messaging, document_dto, create_dto
):
    document_repo.get_by_id.return_value = document_dto
    storage.object_exists.return_value = True
    messaging.queue_depth.return_value = 11

    with pytest.raises(BackpressureException):
        await job_service.create(session, create_dto)


async def test_create_success_when_depth_below_threshold(
    session,
    job_service,
    document_repo,
    storage,
    messaging,
    job_repo,
    document_dto,
    job_dto,
    create_dto,
):
    document_repo.get_by_id.return_value = document_dto
    storage.object_exists.return_value = True
    messaging.queue_depth.return_value = 9  # < backpressure_threshold=10
    job_repo.create.return_value = job_dto

    result = await job_service.create(session, create_dto)

    assert result == job_dto
    job_repo.create.assert_called_once()
    messaging.enqueue.assert_called_once_with(
        "jobs",
        {
            "job_id": job_dto.id,
            "document_id": job_dto.document_id,
            "artifact_types": [ArtifactType.MARKDOWN.value],
        },
    )


async def test_create_propagates_queue_exception_after_commit(
    session,
    job_service,
    document_repo,
    storage,
    messaging,
    job_repo,
    document_dto,
    job_dto,
    create_dto,
):
    document_repo.get_by_id.return_value = document_dto
    storage.object_exists.return_value = True
    messaging.queue_depth.return_value = 9
    job_repo.create.return_value = job_dto
    messaging.enqueue.side_effect = QueueException()

    # Job was committed to DB before enqueue raised; only the exception surfaces here.
    with pytest.raises(QueueException):
        await job_service.create(session, create_dto)


async def test_get_returns_dto(session, job_service, job_repo, job_dto):
    job_repo.get_by_id.return_value = job_dto

    result = await job_service.get(session, job_id=10, account_id=1)

    assert result == job_dto


async def test_get_returns_none_when_not_found(session, job_service, job_repo):
    job_repo.get_by_id.return_value = None

    result = await job_service.get(session, job_id=99, account_id=1)

    assert result is None
```

- [ ] **Step 2: Run and verify all nine tests pass**

```bash
poetry run pytest tests/unit/api/services/test_job_service.py -v
```

Expected:
```
test_create_raises_when_document_not_found PASSED
test_create_raises_when_document_not_uploaded PASSED
test_create_propagates_storage_exception_on_exists_check PASSED
test_create_raises_backpressure_when_depth_at_threshold PASSED
test_create_raises_backpressure_when_depth_above_threshold PASSED
test_create_success_when_depth_below_threshold PASSED
test_create_propagates_queue_exception_after_commit PASSED
test_get_returns_dto PASSED
test_get_returns_none_when_not_found PASSED
9 passed
```

- [ ] **Step 3: Commit**

```bash
git add tests/unit/api/services/test_job_service.py
git commit -m "test: add JobService unit tests"
```

---

## Task 6: ArtifactService Tests

**Files:**
- Create: `tests/unit/api/services/test_artifact_service.py`

- [ ] **Step 1: Create `tests/unit/api/services/test_artifact_service.py`**

```python
from datetime import datetime

import pytest

from shared.core.exceptions import DocumentNotFoundException, StorageException
from shared.dtos.artifact import ArtifactDTO, ArtifactType, ArtifactWithUrlDTO
from shared.dtos.document import DocumentDTO


@pytest.fixture
def document_dto():
    return DocumentDTO(
        id=1,
        object_key="uploads/1.pdf",
        file_name="test.pdf",
        account_id=1,
        created_at=datetime(2026, 1, 1),
    )


def _make_artifact(id_: int, key: str) -> ArtifactDTO:
    return ArtifactDTO(
        id=id_,
        job_id=10,
        document_id=1,
        artifact_type=ArtifactType.MARKDOWN,
        object_key=key,
        created_at=datetime(2026, 1, 1),
    )


async def test_list_raises_when_document_not_found(
    session, artifact_service, document_repo
):
    document_repo.get_by_id.return_value = None

    with pytest.raises(DocumentNotFoundException):
        await artifact_service.list_for_document(session, document_id=1, account_id=1)


async def test_list_returns_empty_for_no_artifacts(
    session, artifact_service, document_repo, artifact_repo, document_dto
):
    document_repo.get_by_id.return_value = document_dto
    artifact_repo.list_by_document_id.return_value = []

    result = await artifact_service.list_for_document(
        session, document_id=1, account_id=1
    )

    assert result == []


async def test_list_returns_artifact_with_url_per_artifact(
    session, artifact_service, document_repo, artifact_repo, storage, document_dto
):
    a1 = _make_artifact(1, "artifacts/1.md")
    a2 = _make_artifact(2, "artifacts/2.md")
    document_repo.get_by_id.return_value = document_dto
    artifact_repo.list_by_document_id.return_value = [a1, a2]
    storage.generate_download_url.side_effect = ["https://url1", "https://url2"]

    result = await artifact_service.list_for_document(
        session, document_id=1, account_id=1
    )

    assert len(result) == 2
    assert result[0] == ArtifactWithUrlDTO(artifact=a1, download_url="https://url1")
    assert result[1] == ArtifactWithUrlDTO(artifact=a2, download_url="https://url2")
    assert storage.generate_download_url.call_count == 2


async def test_list_propagates_storage_exception_mid_loop(
    session, artifact_service, document_repo, artifact_repo, storage, document_dto
):
    a1 = _make_artifact(1, "artifacts/1.md")
    document_repo.get_by_id.return_value = document_dto
    artifact_repo.list_by_document_id.return_value = [a1]
    storage.generate_download_url.side_effect = StorageException()

    with pytest.raises(StorageException):
        await artifact_service.list_for_document(session, document_id=1, account_id=1)
```

- [ ] **Step 2: Run and verify all four tests pass**

```bash
poetry run pytest tests/unit/api/services/test_artifact_service.py -v
```

Expected:
```
test_list_raises_when_document_not_found PASSED
test_list_returns_empty_for_no_artifacts PASSED
test_list_returns_artifact_with_url_per_artifact PASSED
test_list_propagates_storage_exception_mid_loop PASSED
4 passed
```

- [ ] **Step 3: Commit**

```bash
git add tests/unit/api/services/test_artifact_service.py
git commit -m "test: add ArtifactService unit tests"
```

---

## Task 7: RabbitMQMessagingService Tests

**Files:**
- Create: `tests/unit/shared/infrastructure/messaging/test_rabbitmq_messaging_service.py`

**Mock strategy:**
- For `_get_connection` tests: patch `aio_pika.connect_robust` at the module path `shared.infrastructure.messaging.rabbitmq_client.aio_pika.connect_robust`. Set `service._connection` to a mock or `None` to control the branch under test.
- For `enqueue` and `queue_depth` tests: inject a pre-configured `mock_connection` directly via `service._connection = mock_connection`, bypassing `_get_connection`. The channel is an async context manager — `connection.channel()` returns a sync object whose `__aenter__` yields the mock channel.
- For `ChannelClosed`: use `__new__` to create an instance without calling `__init__` (which requires positional args that vary by aio_pika version).

- [ ] **Step 1: Create `tests/unit/shared/infrastructure/messaging/test_rabbitmq_messaging_service.py`**

```python
import pytest
import aio_pika

from shared.core.exceptions import QueueException
from shared.infrastructure.messaging.rabbitmq_client import RabbitMQMessagingService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_channel_cm(mocker):
    """Return (channel_mock, context_manager) wired for `async with conn.channel() as ch`."""
    channel = mocker.AsyncMock()
    cm = mocker.MagicMock()
    cm.__aenter__ = mocker.AsyncMock(return_value=channel)
    cm.__aexit__ = mocker.AsyncMock(return_value=False)
    return channel, cm


def _open_connection(mocker, channel_cm):
    """Return a mock connection that is open and yields channel_cm from .channel()."""
    conn = mocker.MagicMock()
    conn.is_closed = False
    conn.channel.return_value = channel_cm
    return conn


# ---------------------------------------------------------------------------
# _get_connection
# ---------------------------------------------------------------------------


async def test_get_connection_creates_when_none(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    assert svc._connection is None

    mock_conn = mocker.MagicMock()
    mocker.patch("aio_pika.connect_robust", return_value=mock_conn)

    result = await svc._get_connection()

    assert result is mock_conn
    assert svc._connection is mock_conn


async def test_get_connection_reuses_open_connection(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    existing = mocker.MagicMock()
    existing.is_closed = False
    svc._connection = existing

    patch = mocker.patch("aio_pika.connect_robust")

    result = await svc._get_connection()

    assert result is existing
    patch.assert_not_called()


async def test_get_connection_creates_new_when_closed(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    old_conn = mocker.MagicMock()
    old_conn.is_closed = True
    svc._connection = old_conn

    new_conn = mocker.MagicMock()
    mocker.patch("aio_pika.connect_robust", return_value=new_conn)

    result = await svc._get_connection()

    assert result is new_conn
    assert svc._connection is new_conn


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------


async def test_enqueue_success(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    channel, cm = _make_channel_cm(mocker)
    svc._connection = _open_connection(mocker, cm)

    await svc.enqueue("jobs", {"job_id": 1})

    channel.declare_queue.assert_called_once_with("jobs", durable=True)
    channel.default_exchange.publish.assert_called_once()


async def test_enqueue_raises_queue_exception_on_amqp_error(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    channel, cm = _make_channel_cm(mocker)
    channel.declare_queue.side_effect = aio_pika.exceptions.AMQPError()
    svc._connection = _open_connection(mocker, cm)

    with pytest.raises(QueueException):
        await svc.enqueue("jobs", {"job_id": 1})


# ---------------------------------------------------------------------------
# queue_depth
# ---------------------------------------------------------------------------


async def test_queue_depth_returns_message_count(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    channel, cm = _make_channel_cm(mocker)
    declared = mocker.MagicMock()
    declared.declaration_result.message_count = 5
    channel.declare_queue.return_value = declared
    svc._connection = _open_connection(mocker, cm)

    result = await svc.queue_depth("jobs")

    assert result == 5
    channel.declare_queue.assert_called_once_with("jobs", passive=True)


async def test_queue_depth_returns_zero_on_channel_closed(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    channel, cm = _make_channel_cm(mocker)
    # Bypass __init__ — ChannelClosed requires positional args that vary by version.
    exc = aio_pika.exceptions.ChannelClosed.__new__(aio_pika.exceptions.ChannelClosed)
    channel.declare_queue.side_effect = exc
    svc._connection = _open_connection(mocker, cm)

    result = await svc.queue_depth("jobs")

    assert result == 0


async def test_queue_depth_raises_queue_exception_on_amqp_error(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    channel, cm = _make_channel_cm(mocker)
    channel.declare_queue.side_effect = aio_pika.exceptions.AMQPError()
    svc._connection = _open_connection(mocker, cm)

    with pytest.raises(QueueException):
        await svc.queue_depth("jobs")
```

- [ ] **Step 2: Run and verify all eight tests pass**

```bash
poetry run pytest tests/unit/shared/infrastructure/messaging/test_rabbitmq_messaging_service.py -v
```

Expected:
```
test_get_connection_creates_when_none PASSED
test_get_connection_reuses_open_connection PASSED
test_get_connection_creates_new_when_closed PASSED
test_enqueue_success PASSED
test_enqueue_raises_queue_exception_on_amqp_error PASSED
test_queue_depth_returns_message_count PASSED
test_queue_depth_returns_zero_on_channel_closed PASSED
test_queue_depth_raises_queue_exception_on_amqp_error PASSED
8 passed
```

> **Note:** If `ChannelClosed.__new__` doesn't satisfy the `except ChannelClosed` clause (unlikely but possible if aio_pika overrides `__new__`), replace it with a local no-arg subclass:
> ```python
> class _ChannelClosed(aio_pika.exceptions.ChannelClosed):
>     def __init__(self): Exception.__init__(self)
> exc = _ChannelClosed()
> ```

- [ ] **Step 3: Run the full unit suite to confirm nothing interferes**

```bash
poetry run pytest tests/unit/ -v
```

Expected: `27 passed`

- [ ] **Step 4: Commit**

```bash
git add tests/unit/shared/
git commit -m "test: add RabbitMQMessagingService unit tests"
```
