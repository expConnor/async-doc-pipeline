# Phase 2 — Unit Tests: Worker Services

## Scope

Unit tests for `ProcessingService` and `RabbitMQConsumer` (`_handle` and `_handle_failure`). All interface dependencies are mocked. No real DB, S3, or RabbitMQ connections.

## File Layout

```
tests/unit/worker/
    __init__.py
    conftest.py
    services/
        __init__.py
        test_processing_service.py
    infrastructure/
        messaging/
            __init__.py
            test_consumer.py
```

Mirrors the source tree, consistent with Phase 1 (`tests/unit/api/services/`, `tests/unit/shared/infrastructure/messaging/`).

## Conftest Fixtures (`tests/unit/worker/conftest.py`)

`session` is inherited from `tests/unit/conftest.py`.

| Fixture | Type | Notes |
|---|---|---|
| `job_repo` | `mocker.AsyncMock()` | |
| `document_repo` | `mocker.AsyncMock()` | |
| `artifact_repo` | `mocker.AsyncMock()` | |
| `storage` | `mocker.AsyncMock()` | |
| `parser` | `mocker.AsyncMock()` | Worker-specific |
| `processing_service` | `ProcessingService(...)` | Wired with all five mocks above |
| `messaging` | `mocker.AsyncMock()` | |
| `container` | `mocker.MagicMock()` | `open_session` configured as async CM yielding `session` |
| `consumer` | `RabbitMQConsumer(...)` | Wired with container, processing_service, messaging, job_repo |

`container.open_session` is a `MagicMock` whose return value is configured with `__aenter__` returning `session` and `__aexit__` returning `False`. This means all three `open_session` calls in `_handle` yield the same `session` mock, which is sufficient for unit tests.

For the one test where `open_session` itself must raise, set `container.open_session.side_effect` inline in that test.

## `test_processing_service.py`

Local fixtures: `job_dto` (status=STARTED, document_id=1, account_id=1, id=10) and `document_dto` (file_name varies per test).

| Test | Setup | Asserts |
|---|---|---|
| `test_job_not_found_raises` | `job_repo.get_for_processing` → `None` | raises `JobNotFoundException` |
| `test_document_not_found_raises` | job found, `document_repo.get_by_id` → `None` | raises `DocumentNotFoundException` |
| `test_get_object_storage_exception_propagates` | doc found, `storage.get_object` raises `StorageException` | propagates |
| `test_parser_exception_propagates` | get_object succeeds, `parser.parse` raises `RuntimeError` | propagates |
| `test_put_object_storage_exception_propagates` | parse succeeds, `storage.put_object` raises `StorageException` | propagates |
| `test_artifact_create_exception_propagates` | put_object succeeds, `artifact_repo.create` raises `DatabaseException` | propagates |
| `test_success_creates_artifact_and_completes_job` | all succeed | `artifact_repo.create` called with correct `CreateArtifactDTO`; `job_repo.update_status` called with `COMPLETED, expected_status=STARTED` |
| `test_artifact_key_simple` | `file_name="report.pdf"`, `job_id=10` | key = `"artifacts/10/report.md"` |
| `test_artifact_key_dotted_stem` | `file_name="my.report.pdf"`, `job_id=10` | key = `"artifacts/10/my.report.md"` |
| `test_artifact_key_no_extension` | `file_name="report"`, `job_id=10` | key = `"artifacts/10/report.md"` |

Artifact key tests assert the `object_key` argument passed to `artifact_repo.create` via `call_args`.

## `test_consumer.py`

Local fixture: `msg` (`mocker.AsyncMock()`). `msg.body` is set per test.

### `_handle` tests

| Test | Setup | Asserts |
|---|---|---|
| `test_handle_bad_json_acks` | `msg.body = b"not json"` | `msg.ack()` called; no repo calls |
| `test_handle_missing_job_id_acks` | `msg.body = b'{"foo": 1}'` | `msg.ack()` called; no repo calls |
| `test_handle_null_job_id_acks` | `msg.body = b'{"job_id": null}'` | `job_repo.get_for_processing` called with `None`; returns `None` → `msg.ack()` |
| `test_handle_job_not_found_acks` | valid JSON, `job_repo.get_for_processing` → `None` | `msg.ack()` called |
| `test_handle_job_not_queued_acks` | job with `status=STARTED` | `msg.ack()` called; no STARTED transition attempted |
| `test_handle_concurrent_claim_acks` | QUEUED job; `update_status` raises `JobStateConflictException` | `msg.ack()` called |
| `test_handle_started_db_error_nacks` | QUEUED job; `update_status` raises `DatabaseException` | `msg.nack(requeue=True)` called |
| `test_handle_open_session_raises_propagates` | `container.open_session.side_effect = RuntimeError` | `RuntimeError` propagates; no ack |
| `test_handle_processing_success_acks` | all succeed | `msg.ack()` called; `processing_service.process` called once |
| `test_handle_processing_failure_delegates` | `processing_service.process` raises `RuntimeError` | `msg.ack()` called; `job_repo.update_status` called to mark failure (via `_handle_failure` — use exhausted attempts to keep it deterministic) |

For `update_status` tests: `job_repo.get_for_processing` returns a QUEUED job; `job_repo.update_status.side_effect` drives the failure. The same `session` mock is used for all `open_session` calls.

### `_handle_failure` tests

Called directly: `await consumer._handle_failure(job_id, attempts, max_attempts, exc)`.

| Test | Setup | Asserts |
|---|---|---|
| `test_failure_below_max_requeues` | `attempts=1, max_attempts=3` | `update_status(QUEUED, expected_status=STARTED)` called; `messaging.enqueue` called |
| `test_failure_at_max_terminal` | `attempts=3, max_attempts=3` | `update_status(FAILED, expected_status=STARTED)` called; `messaging.enqueue` NOT called |
| `test_failure_above_max_terminal` | `attempts=4, max_attempts=3` | same as at-max |
| `test_failure_reenqueue_queue_exception_logged` | `attempts=1, max_attempts=3`; `messaging.enqueue` raises `QueueException` | no re-raise; `update_status(QUEUED)` was called |
| `test_failure_update_failed_db_exception_propagates` | `attempts=3, max_attempts=3`; `update_status` raises `DatabaseException` | `DatabaseException` propagates out of `_handle_failure` |
| `test_failure_update_state_conflict_logged` | `update_status` raises `JobStateConflictException` | no re-raise (caught by outer `try/except JobStateConflictException`) |

## Mocking Strategy

- **Default**: drive all failures through repo/service `side_effect`. Same `session` mock across all `open_session` calls within a single `_handle` invocation.
- **Exception**: for `test_handle_open_session_raises_propagates`, set `container.open_session.side_effect` inline in that test only.
