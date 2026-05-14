# Phase 2 — Unit Tests: Worker Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write unit tests for `ProcessingService` and `RabbitMQConsumer._handle`/`_handle_failure`, covering all branches with all dependencies mocked.

**Architecture:** Tests live in `tests/unit/worker/`, mirroring the source tree. A shared conftest at `tests/unit/worker/conftest.py` provides all mock fixtures. `test_processing_service.py` calls `process()` directly with a mock session; `test_consumer.py` calls `_handle`/`_handle_failure` directly with mock messages and overrides `processing_service` with a local `AsyncMock`.

**Tech Stack:** pytest, pytest-asyncio (asyncio_mode = "auto"), pytest-mock (`mocker` fixture)

---

## File Map

| File | Action |
|---|---|
| `tests/unit/worker/__init__.py` | Create (empty) |
| `tests/unit/worker/conftest.py` | Create — shared fixtures for all worker tests |
| `tests/unit/worker/services/__init__.py` | Create (empty) |
| `tests/unit/worker/services/test_processing_service.py` | Create |
| `tests/unit/worker/infrastructure/__init__.py` | Create (empty) |
| `tests/unit/worker/infrastructure/messaging/__init__.py` | Create (empty) |
| `tests/unit/worker/infrastructure/messaging/test_consumer.py` | Create |

---

### Task 1: Scaffold + conftest

**Files:**
- Create: `tests/unit/worker/__init__.py`
- Create: `tests/unit/worker/conftest.py`
- Create: `tests/unit/worker/services/__init__.py`
- Create: `tests/unit/worker/infrastructure/__init__.py`
- Create: `tests/unit/worker/infrastructure/messaging/__init__.py`

- [ ] **Step 1: Create empty `__init__.py` files**

```bash
touch tests/unit/worker/__init__.py \
      tests/unit/worker/services/__init__.py \
      tests/unit/worker/infrastructure/__init__.py \
      tests/unit/worker/infrastructure/messaging/__init__.py
```

- [ ] **Step 2: Create `tests/unit/worker/conftest.py`**

```python
import pytest

from worker.infrastructure.messaging.consumer import RabbitMQConsumer
from worker.services.processing_service import ProcessingService


@pytest.fixture
def job_repo(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def document_repo(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def artifact_repo(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def storage(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def parser(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def messaging(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def processing_service(job_repo, document_repo, artifact_repo, storage, parser):
    return ProcessingService(
        job_repo=job_repo,
        document_repo=document_repo,
        artifact_repo=artifact_repo,
        storage=storage,
        parser=parser,
    )


@pytest.fixture
def container(mocker, session):
    c = mocker.MagicMock()
    cm = mocker.MagicMock()
    cm.__aenter__ = mocker.AsyncMock(return_value=session)
    cm.__aexit__ = mocker.AsyncMock(return_value=False)
    c.open_session.return_value = cm
    return c


@pytest.fixture
def consumer(container, processing_service, messaging, job_repo):
    return RabbitMQConsumer(
        container=container,
        processing_service=processing_service,
        messaging=messaging,
        job_repo=job_repo,
        url="amqp://localhost/",
        queue="jobs",
    )
```

The `session` fixture is inherited from `tests/unit/conftest.py` (already exists). The `container` fixture wires `open_session` as an async context manager: every `async with container.open_session() as s` yields the same `session` mock — correct for unit tests. For tests where `open_session` itself must raise, set `container.open_session.side_effect` inline in that test.

- [ ] **Step 3: Verify the scaffold collects cleanly**

```bash
pytest tests/unit/worker/ --collect-only
```

Expected: `0 tests collected` with no import errors.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/worker/
git commit -m "test: scaffold worker unit test directory and conftest"
```

---

### Task 2: ProcessingService — error path tests

**Files:**
- Create: `tests/unit/worker/services/test_processing_service.py`

- [ ] **Step 1: Create `tests/unit/worker/services/test_processing_service.py`**

```python
from datetime import datetime

import pytest

from shared.core.exceptions import (
    DatabaseException,
    DocumentNotFoundException,
    JobNotFoundException,
    StorageException,
)
from shared.dtos.artifact import ArtifactType
from shared.dtos.document import DocumentDTO
from shared.dtos.job import JobDTO, JobStatus


@pytest.fixture
def job_dto():
    return JobDTO(
        id=10,
        account_id=1,
        document_id=1,
        status=JobStatus.STARTED,
        artifact_types=[ArtifactType.MARKDOWN],
        attempts=1,
        max_attempts=3,
        error_message=None,
        created_at=datetime(2026, 1, 1),
        queued_at=datetime(2026, 1, 1),
        started_at=datetime(2026, 1, 1),
        completed_at=None,
        last_attempt_at=None,
        failed_at=None,
    )


@pytest.fixture
def document_dto():
    return DocumentDTO(
        id=1,
        object_key="uploads/1/report.pdf",
        file_name="report.pdf",
        account_id=1,
        created_at=datetime(2026, 1, 1),
    )


async def test_job_not_found_raises(session, processing_service, job_repo):
    job_repo.get_for_processing.return_value = None

    with pytest.raises(JobNotFoundException):
        await processing_service.process(session, 10)


async def test_document_not_found_raises(
    session, processing_service, job_repo, document_repo, job_dto
):
    job_repo.get_for_processing.return_value = job_dto
    document_repo.get_by_id.return_value = None

    with pytest.raises(DocumentNotFoundException):
        await processing_service.process(session, 10)


async def test_get_object_storage_exception_propagates(
    session, processing_service, job_repo, document_repo, storage, job_dto, document_dto
):
    job_repo.get_for_processing.return_value = job_dto
    document_repo.get_by_id.return_value = document_dto
    storage.get_object.side_effect = StorageException()

    with pytest.raises(StorageException):
        await processing_service.process(session, 10)


async def test_parser_exception_propagates(
    session, processing_service, job_repo, document_repo, storage, parser, job_dto, document_dto
):
    job_repo.get_for_processing.return_value = job_dto
    document_repo.get_by_id.return_value = document_dto
    storage.get_object.return_value = b"pdf content"
    parser.parse.side_effect = RuntimeError("parse failed")

    with pytest.raises(RuntimeError, match="parse failed"):
        await processing_service.process(session, 10)


async def test_put_object_storage_exception_propagates(
    session, processing_service, job_repo, document_repo, storage, parser, job_dto, document_dto
):
    job_repo.get_for_processing.return_value = job_dto
    document_repo.get_by_id.return_value = document_dto
    storage.get_object.return_value = b"pdf content"
    parser.parse.return_value = "# Markdown"
    storage.put_object.side_effect = StorageException()

    with pytest.raises(StorageException):
        await processing_service.process(session, 10)


async def test_artifact_create_exception_propagates(
    session,
    processing_service,
    job_repo,
    document_repo,
    storage,
    parser,
    artifact_repo,
    job_dto,
    document_dto,
):
    job_repo.get_for_processing.return_value = job_dto
    document_repo.get_by_id.return_value = document_dto
    storage.get_object.return_value = b"pdf content"
    parser.parse.return_value = "# Markdown"
    artifact_repo.create.side_effect = DatabaseException()

    with pytest.raises(DatabaseException):
        await processing_service.process(session, 10)
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/unit/worker/services/test_processing_service.py -v
```

Expected: `6 passed`.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/worker/services/test_processing_service.py
git commit -m "test: add ProcessingService error path unit tests"
```

---

### Task 3: ProcessingService — success and artifact key tests

**Files:**
- Modify: `tests/unit/worker/services/test_processing_service.py`

- [ ] **Step 1: Add the following imports to the top of the file** (add to existing import block)

```python
from shared.dtos.artifact import ArtifactType, CreateArtifactDTO  # add CreateArtifactDTO
```

- [ ] **Step 2: Append the following tests to the bottom of `test_processing_service.py`**

```python
async def test_success_creates_artifact_and_completes_job(
    session,
    processing_service,
    job_repo,
    document_repo,
    storage,
    parser,
    artifact_repo,
    job_dto,
    document_dto,
):
    job_repo.get_for_processing.return_value = job_dto
    document_repo.get_by_id.return_value = document_dto
    storage.get_object.return_value = b"pdf content"
    parser.parse.return_value = "# Markdown"

    await processing_service.process(session, 10)

    artifact_repo.create.assert_called_once_with(
        session,
        CreateArtifactDTO(10, 1, ArtifactType.MARKDOWN, "artifacts/10/report.md"),
    )
    job_repo.update_status.assert_called_once_with(
        session,
        10,
        JobStatus.COMPLETED,
        expected_status=JobStatus.STARTED,
    )


@pytest.mark.parametrize(
    "file_name,expected_key",
    [
        ("report.pdf", "artifacts/10/report.md"),
        ("my.report.pdf", "artifacts/10/my.report.md"),
        ("report", "artifacts/10/report.md"),
    ],
)
async def test_artifact_key_format(
    session,
    processing_service,
    job_repo,
    document_repo,
    storage,
    parser,
    artifact_repo,
    job_dto,
    file_name,
    expected_key,
):
    doc = DocumentDTO(
        id=1,
        object_key="uploads/1/doc",
        file_name=file_name,
        account_id=1,
        created_at=datetime(2026, 1, 1),
    )
    job_repo.get_for_processing.return_value = job_dto
    document_repo.get_by_id.return_value = doc
    storage.get_object.return_value = b"pdf content"
    parser.parse.return_value = "# Markdown"

    await processing_service.process(session, 10)

    _, dto = artifact_repo.create.call_args.args
    assert dto.object_key == expected_key
```

`Path("my.report.pdf").stem` is `"my.report"` — the parametrized cases verify that `Path.stem` strips only the last extension, which is the actual production behavior.

- [ ] **Step 3: Run all processing service tests**

```bash
pytest tests/unit/worker/services/test_processing_service.py -v
```

Expected: `10 passed` (6 from Task 2 + 1 success + 3 parametrized key tests).

- [ ] **Step 4: Commit**

```bash
git add tests/unit/worker/services/test_processing_service.py
git commit -m "test: add ProcessingService success and artifact key unit tests"
```

---

### Task 4: Consumer — `_handle` poison message and job-not-found tests

**Files:**
- Create: `tests/unit/worker/infrastructure/messaging/test_consumer.py`

The `processing_service` fixture defined locally here shadows the conftest's real `ProcessingService` with an `AsyncMock`. This is intentional: consumer tests verify `_handle` logic, not the processing pipeline.

- [ ] **Step 1: Create `tests/unit/worker/infrastructure/messaging/test_consumer.py`**

```python
from datetime import datetime

import pytest

from shared.dtos.artifact import ArtifactType
from shared.dtos.job import JobDTO, JobStatus


@pytest.fixture
def processing_service(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def queued_job_dto():
    return JobDTO(
        id=10,
        account_id=1,
        document_id=1,
        status=JobStatus.QUEUED,
        artifact_types=[ArtifactType.MARKDOWN],
        attempts=1,
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
def started_job_dto():
    # attempts == max_attempts: makes _handle_failure take the terminal path,
    # keeping failure-delegation tests deterministic without chaining mocks.
    return JobDTO(
        id=10,
        account_id=1,
        document_id=1,
        status=JobStatus.STARTED,
        artifact_types=[ArtifactType.MARKDOWN],
        attempts=3,
        max_attempts=3,
        error_message=None,
        created_at=datetime(2026, 1, 1),
        queued_at=datetime(2026, 1, 1),
        started_at=datetime(2026, 1, 1),
        completed_at=None,
        last_attempt_at=None,
        failed_at=None,
    )


@pytest.fixture
def msg(mocker):
    return mocker.AsyncMock()


async def test_handle_bad_json_acks(consumer, msg, job_repo):
    msg.body = b"not json"

    await consumer._handle(msg)

    msg.ack.assert_called_once()
    job_repo.get_for_processing.assert_not_called()


async def test_handle_missing_job_id_acks(consumer, msg, job_repo):
    msg.body = b'{"foo": 1}'

    await consumer._handle(msg)

    msg.ack.assert_called_once()
    job_repo.get_for_processing.assert_not_called()


async def test_handle_null_job_id_acks(consumer, msg, job_repo):
    # null JSON → job_id = None; code does not raise, falls through to repo lookup
    msg.body = b'{"job_id": null}'
    job_repo.get_for_processing.return_value = None

    await consumer._handle(msg)

    assert job_repo.get_for_processing.call_args.args[1] is None
    msg.ack.assert_called_once()


async def test_handle_job_not_found_acks(consumer, msg, job_repo):
    msg.body = b'{"job_id": 10}'
    job_repo.get_for_processing.return_value = None

    await consumer._handle(msg)

    msg.ack.assert_called_once()


async def test_handle_job_not_queued_acks(consumer, msg, job_repo, started_job_dto):
    msg.body = b'{"job_id": 10}'
    job_repo.get_for_processing.return_value = started_job_dto

    await consumer._handle(msg)

    job_repo.update_status.assert_not_called()
    msg.ack.assert_called_once()
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/unit/worker/infrastructure/messaging/test_consumer.py -v
```

Expected: `5 passed`.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/worker/infrastructure/messaging/test_consumer.py
git commit -m "test: add RabbitMQConsumer _handle poison and job-not-found tests"
```

---

### Task 5: Consumer — `_handle` STARTED transition tests

**Files:**
- Modify: `tests/unit/worker/infrastructure/messaging/test_consumer.py`

- [ ] **Step 1: Append the following to `test_consumer.py`**

```python
from shared.core.exceptions import DatabaseException, JobStateConflictException


async def test_handle_concurrent_claim_acks(consumer, msg, job_repo, queued_job_dto):
    msg.body = b'{"job_id": 10}'
    job_repo.get_for_processing.return_value = queued_job_dto
    job_repo.update_status.side_effect = JobStateConflictException()

    await consumer._handle(msg)

    msg.ack.assert_called_once()
    msg.nack.assert_not_called()


async def test_handle_started_db_error_nacks(consumer, msg, job_repo, queued_job_dto):
    msg.body = b'{"job_id": 10}'
    job_repo.get_for_processing.return_value = queued_job_dto
    job_repo.update_status.side_effect = DatabaseException()

    await consumer._handle(msg)

    msg.nack.assert_called_once_with(requeue=True)
    msg.ack.assert_not_called()


async def test_handle_open_session_raises_propagates(consumer, msg):
    msg.body = b'{"job_id": 10}'
    consumer._container.open_session.side_effect = RuntimeError("db down")

    with pytest.raises(RuntimeError, match="db down"):
        await consumer._handle(msg)

    msg.ack.assert_not_called()
    msg.nack.assert_not_called()
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/unit/worker/infrastructure/messaging/test_consumer.py -v
```

Expected: `8 passed`.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/worker/infrastructure/messaging/test_consumer.py
git commit -m "test: add RabbitMQConsumer _handle STARTED transition tests"
```

---

### Task 6: Consumer — `_handle` success and failure delegation tests

**Files:**
- Modify: `tests/unit/worker/infrastructure/messaging/test_consumer.py`

- [ ] **Step 1: Append the following to `test_consumer.py`**

```python
async def test_handle_processing_success_acks(
    consumer, msg, job_repo, processing_service, queued_job_dto, started_job_dto
):
    msg.body = b'{"job_id": 10}'
    job_repo.get_for_processing.return_value = queued_job_dto
    job_repo.update_status.return_value = started_job_dto

    await consumer._handle(msg)

    processing_service.process.assert_called_once()
    msg.ack.assert_called_once()
    msg.nack.assert_not_called()


async def test_handle_processing_failure_delegates(
    consumer, msg, job_repo, processing_service, queued_job_dto, started_job_dto, session
):
    # started_job_dto has attempts=max_attempts=3, so _handle_failure takes the
    # terminal path (FAILED), keeping this test simple without chaining mocks.
    msg.body = b'{"job_id": 10}'
    job_repo.get_for_processing.return_value = queued_job_dto
    job_repo.update_status.return_value = started_job_dto
    processing_service.process.side_effect = RuntimeError("processing failed")

    await consumer._handle(msg)

    job_repo.update_status.assert_called_with(
        session,
        10,
        JobStatus.FAILED,
        expected_status=JobStatus.STARTED,
        error_message="processing failed",
    )
    msg.ack.assert_called_once()
```

`assert_called_with` checks the most recent call. `update_status` is called twice here: once for STARTED (by `_handle`) and once for FAILED (by `_handle_failure`). The assertion verifies the FAILED call.

- [ ] **Step 2: Run tests**

```bash
pytest tests/unit/worker/infrastructure/messaging/test_consumer.py -v
```

Expected: `10 passed`.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/worker/infrastructure/messaging/test_consumer.py
git commit -m "test: add RabbitMQConsumer _handle success and failure delegation tests"
```

---

### Task 7: Consumer — `_handle_failure` tests

**Files:**
- Modify: `tests/unit/worker/infrastructure/messaging/test_consumer.py`

- [ ] **Step 1: Append the following to `test_consumer.py`**

```python
from shared.core.exceptions import DatabaseException, JobStateConflictException, QueueException


async def test_failure_below_max_requeues(consumer, job_repo, messaging, session):
    await consumer._handle_failure(10, 1, 3, RuntimeError("failed"))

    job_repo.update_status.assert_called_once_with(
        session,
        10,
        JobStatus.QUEUED,
        expected_status=JobStatus.STARTED,
        error_message="failed",
    )
    messaging.enqueue.assert_called_once_with("jobs", {"job_id": 10})


async def test_failure_at_max_terminal(consumer, job_repo, messaging, session):
    await consumer._handle_failure(10, 3, 3, RuntimeError("failed"))

    job_repo.update_status.assert_called_once_with(
        session,
        10,
        JobStatus.FAILED,
        expected_status=JobStatus.STARTED,
        error_message="failed",
    )
    messaging.enqueue.assert_not_called()


async def test_failure_above_max_terminal(consumer, job_repo, messaging, session):
    await consumer._handle_failure(10, 4, 3, RuntimeError("failed"))

    job_repo.update_status.assert_called_once_with(
        session,
        10,
        JobStatus.FAILED,
        expected_status=JobStatus.STARTED,
        error_message="failed",
    )
    messaging.enqueue.assert_not_called()


async def test_failure_reenqueue_queue_exception_logged(consumer, job_repo, messaging, session):
    messaging.enqueue.side_effect = QueueException()

    await consumer._handle_failure(10, 1, 3, RuntimeError("failed"))

    job_repo.update_status.assert_called_once_with(
        session,
        10,
        JobStatus.QUEUED,
        expected_status=JobStatus.STARTED,
        error_message="failed",
    )
    # QueueException is caught and logged — completing without raising is the assertion


async def test_failure_update_failed_db_exception_propagates(consumer, job_repo):
    job_repo.update_status.side_effect = DatabaseException()

    with pytest.raises(DatabaseException):
        await consumer._handle_failure(10, 3, 3, RuntimeError("failed"))


async def test_failure_update_state_conflict_logged(consumer, job_repo):
    job_repo.update_status.side_effect = JobStateConflictException()

    # JobStateConflictException is caught by the outer try/except — no propagation
    await consumer._handle_failure(10, 3, 3, RuntimeError("failed"))
```

- [ ] **Step 2: Run all worker unit tests**

```bash
pytest tests/unit/worker/ -v
```

Expected: `26 passed` (10 processing service + 16 consumer).

- [ ] **Step 3: Run the full unit test suite to check for regressions**

```bash
pytest tests/unit/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/worker/infrastructure/messaging/test_consumer.py
git commit -m "test: add RabbitMQConsumer _handle_failure unit tests"
```
