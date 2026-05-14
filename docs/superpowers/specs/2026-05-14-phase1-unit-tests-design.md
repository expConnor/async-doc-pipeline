# Phase 1 Unit Tests: API + Infrastructure Services

## Scope

Unit tests for `AccountService`, `DocumentService`, `JobService`, `ArtifactService`, and `RabbitMQMessagingService`. All interface dependencies are mocked. `APIKeyHeader` is excluded — covered in Phase 4 route tests where HTTP context is already present.

## Toolchain

- `pytest-asyncio` with `asyncio_mode = "auto"` — no per-test marks needed
- `pytest-mock` — `mocker` fixture for all mocks, automatic cleanup

Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## File Layout

Mirrors source layout exactly.

```
tests/
└── unit/
    ├── conftest.py
    ├── api/
    │   └── services/
    │       ├── conftest.py
    │       ├── test_account_service.py
    │       ├── test_document_service.py
    │       ├── test_job_service.py
    │       └── test_artifact_service.py
    └── shared/
        └── infrastructure/
            └── messaging/
                └── test_rabbitmq_messaging_service.py
```

## Fixtures

**`tests/unit/conftest.py`**

```python
@pytest.fixture
def session(mocker):
    return mocker.AsyncMock()
```

**`tests/unit/api/services/conftest.py`**

One fixture per dependency. All repository and infrastructure interfaces are `AsyncMock`.

```python
@pytest.fixture
def account_repo(mocker): return mocker.AsyncMock()

@pytest.fixture
def document_repo(mocker): return mocker.AsyncMock()

@pytest.fixture
def job_repo(mocker): return mocker.AsyncMock()

@pytest.fixture
def artifact_repo(mocker): return mocker.AsyncMock()

@pytest.fixture
def storage(mocker): return mocker.AsyncMock()

@pytest.fixture
def messaging(mocker): return mocker.AsyncMock()

@pytest.fixture
def account_service(account_repo):
    return AccountService(account_repo)

@pytest.fixture
def document_service(document_repo, storage):
    return DocumentService(document_repo, storage)

@pytest.fixture
def job_service(job_repo, document_repo, messaging, storage):
    return JobService(
        job_repo, document_repo, messaging, storage,
        queue="jobs", backpressure_threshold=10,
    )

@pytest.fixture
def artifact_service(artifact_repo, storage, document_repo):
    return ArtifactService(artifact_repo, storage, document_repo)
```

`RabbitMQMessagingService` fixtures are defined inline in its own test file since setup differs (direct `_connection` injection).

## Test Cases

### `AccountService` — 2 tests

SHA-256 accepts any string without error, so key format (empty, non-hex, wrong length) does not change service behavior. Only two meaningful branches exist.

| Test | Setup | Assert |
|---|---|---|
| valid key, repo returns DTO | `repo.get_by_api_key_hash` returns `AccountDTO` | returns DTO; repo called with `sha256(key).hexdigest()` |
| valid key, repo returns None | `repo.get_by_api_key_hash` returns `None` | returns `None` |

### `DocumentService` — 4 tests

| Test | Setup | Assert |
|---|---|---|
| `create` success | repo returns `DocumentDTO`, storage returns URL | returns `DocumentWithUploadUrlDTO` with both |
| `create` storage error | `generate_upload_url` raises `StorageException` | `StorageException` propagates |
| `get` match | `repo.get_by_id` returns `DocumentDTO` | returns DTO |
| `get` no match | `repo.get_by_id` returns `None` | returns `None` |

### `JobService.create` — 7 tests

| Test | Setup | Assert |
|---|---|---|
| document not found | `document_repo.get_by_id` returns `None` | raises `DocumentNotFoundException` |
| document not uploaded | `object_exists` returns `False` | raises `DocumentNotUploadedException` |
| storage error on exists check | `object_exists` raises `StorageException` | `StorageException` propagates |
| depth below threshold | `queue_depth` returns 9, threshold=10 | success; `repo.create` and `messaging.enqueue` called |
| depth at threshold | `queue_depth` returns 10, threshold=10 | raises `BackpressureException` |
| depth above threshold | `queue_depth` returns 11, threshold=10 | raises `BackpressureException` |
| enqueue fails after commit | `messaging.enqueue` raises `QueueException` | `QueueException` propagates |

The enqueue-after-commit failure case documents that the job row exists in the DB when the exception surfaces (commit already ran). The test only asserts the exception type — call ordering is not verified.

### `JobService.get` — 2 tests

| Test | Setup | Assert |
|---|---|---|
| found | `repo.get_by_id` returns `JobDTO` | returns DTO |
| not found | `repo.get_by_id` returns `None` | returns `None` |

### `ArtifactService` — 4 tests

| Test | Setup | Assert |
|---|---|---|
| document not found | `document_repo.get_by_id` returns `None` | raises `DocumentNotFoundException` |
| empty artifact list | `repo.list_by_document_id` returns `[]` | returns `[]` |
| multiple artifacts | returns 2 `ArtifactDTO`s | `generate_download_url` called once per artifact; result is list of `ArtifactWithUrlDTO` |
| storage error mid-loop | `generate_download_url` raises `StorageException` on first artifact | `StorageException` propagates |

### `RabbitMQMessagingService` — 8 tests

Mock strategy: inject `_connection` directly on the service instance for most tests. Only `_get_connection` tests patch `aio_pika.connect_robust` at the module level.

**`_get_connection` — 3 tests**

| Test | Setup | Assert |
|---|---|---|
| connection is `None` | `_connection = None` | `connect_robust` called, result stored on `_connection` |
| connection open | `_connection` is a mock with `is_closed=False` | `connect_robust` not called, existing connection returned |
| connection closed | `_connection` is a mock with `is_closed=True` | `connect_robust` called, new connection stored |

**`enqueue` — 2 tests**

| Test | Setup | Assert |
|---|---|---|
| success | inject mock connection + channel chain | completes without error |
| `AMQPError` | channel operations raise `AMQPError` | raises `QueueException` |

**`queue_depth` — 3 tests**

| Test | Setup | Assert |
|---|---|---|
| success | `declare_queue` returns mock with `declaration_result.message_count = 5` | returns `5` |
| `ChannelClosed` on declare | `declare_queue` raises `ChannelClosed` | returns `0` |
| `AMQPError` | channel raises `AMQPError` | raises `QueueException` |
