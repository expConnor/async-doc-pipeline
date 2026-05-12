# Worker RabbitMQ Consumer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the worker's RabbitMQ consumer so that messages enqueued by the API are pulled, drive `ProcessingService`, and apply the DB-scoped retry policy from CLAUDE.md.

**Architecture:** Thin transport-layer consumer (`RabbitMQConsumer`) owns the consume loop, ack/retry orchestration, and graceful drain. `ProcessingService` is refactored to take only `(session, job_id)` and resolves the job + document internally. The consumer owns the `STARTED` and failure-path transitions; `ProcessingService` only owns `COMPLETED`. Retry uses `IMessagingService.enqueue` (DB-scoped, no RabbitMQ redelivery); no backoff, no DLQ.

**Tech Stack:** Python 3.13, asyncio, aio_pika, SQLAlchemy 2.x async, pymupdf4llm.

**Spec:** `docs/superpowers/specs/2026-05-12-worker-consumer-design.md`.

**Notes for the implementer (Connor):**
- Tests are deferred to end of project — no test steps in this plan. Author by hand at the end.
- Code blocks below are signatures and structural sketches, not full implementations. Implementation choices (variable names, exact control flow, log messages) are yours; just hit the behavior described.
- Spec called for a new `mark_started` repo method, but `JobRepository.update_status(JobStatus.STARTED)` already does the atomic increment + timestamp work (see `shared/infrastructure/repositories/job.py:55-81`). The plan reuses it directly. Flagging here so the spec/plan deviation is explicit.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `shared/interfaces/repositories/job.py` | Modify | Add `get_for_processing(session, job_id)` (no `account_id`). |
| `shared/infrastructure/repositories/job.py` | Modify | Implement `get_for_processing`. |
| `worker/services/processing_service.py` | Modify | Refactor `process` to `(session, job_id)`; load job + document internally; only commits `COMPLETED`. |
| `worker/core/container.py` | Modify | Add `document_repository()`, `messaging_service()`, `consumer()` factories; update `processing_service()` deps. |
| `worker/infrastructure/messaging/consumer.py` | Create | `RabbitMQConsumer` — consume loop, ack/retry, drain. |
| `worker/main.py` | Create | Entry point: signal handlers + `asyncio.run`. |

---

## Task 1: Add `get_for_processing` to `IJobRepository`

The worker has no account context and shouldn't have to fabricate one. Add a worker-side lookup that fetches a job by id only.

**Files:**
- Modify: `shared/interfaces/repositories/job.py`
- Modify: `shared/infrastructure/repositories/job.py`

- [ ] **Step 1: Add abstract method on `IJobRepository`**

Add to `shared/interfaces/repositories/job.py`:

```python
@abstractmethod
async def get_for_processing(
    self, session: Any, job_id: int
) -> JobDTO | None: ...
```

- [ ] **Step 2: Implement on `JobRepository`**

In `shared/infrastructure/repositories/job.py`, add a method that selects `Job` by `id` only (no `account_id` filter), reuses `self._to_dto`, and wraps `SQLAlchemyError` as `DatabaseException` (same pattern as the other methods).

- [ ] **Step 3: Lint + format**

```bash
ruff check . && ruff format .
```

- [ ] **Step 4: Commit**

```bash
git add shared/interfaces/repositories/job.py shared/infrastructure/repositories/job.py
git commit -m "feat: add get_for_processing to job repository"
```

---

## Task 2: Refactor `ProcessingService.process` to `(session, job_id)`

`ProcessingService` should resolve the job and document itself. The consumer stays transport-only. After this task, the service no longer owns the `STARTED` transition — that moves to the consumer (Task 4). The service still owns the `COMPLETED` transition on the success path.

**Files:**
- Modify: `worker/services/processing_service.py`

- [ ] **Step 1: Update the constructor**

`ProcessingService.__init__` gains a `document_repo: IDocumentRepository` dependency alongside the existing `job_repo`, `artifact_repo`, `storage`, `parser`.

- [ ] **Step 2: Update `process` signature**

```python
async def process(self, session: Any, job_id: int) -> None: ...
```

- [ ] **Step 3: Update `process` body**

The new body, in order:

1. `job = await self._job_repo.get_for_processing(session, job_id)` — assume non-None; the consumer guarantees the job exists and is in `QUEUED` state before calling.
2. `document = await self._document_repo.get_by_id(session, job.document_id, job.account_id)` — use the `account_id` from the loaded job.
3. `content = await self._storage.get_object(document.object_key)`.
4. `markdown = await self._parser.parse(content)`.
5. `key = f"artifacts/{job_id}/{Path(document.file_name).stem}.md"`.
6. `await self._storage.put_object(key, markdown.encode())`.
7. `await self._artifact_repo.create(session, CreateArtifactDTO(job_id, job.document_id, ArtifactType.MARKDOWN, key))`.
8. `await self._job_repo.update_status(session, job_id, JobStatus.COMPLETED)`.

Drop the line that sets `STARTED` at the top of the current implementation — the consumer owns that transition.

- [ ] **Step 4: Lint + format**

```bash
ruff check . && ruff format .
```

- [ ] **Step 5: Commit**

```bash
git add worker/services/processing_service.py
git commit -m "refactor: ProcessingService.process resolves job and document internally"
```

---

## Task 3: Wire `document_repository` and `messaging_service` in the container

**Files:**
- Modify: `worker/core/container.py`

- [ ] **Step 1: Add `document_repository()` factory**

Returns `DocumentRepository()` (import from `shared.infrastructure.repositories.document`). Follows the same shape as `job_repository()` and `artifact_repository()`.

- [ ] **Step 2: Add `messaging_service()` factory**

Returns `RabbitMQMessagingService(url=self._settings.rabbitmq_url)` (import from `shared.infrastructure.messaging.rabbitmq_client`). Return type annotation: `IMessagingService`.

- [ ] **Step 3: Update `processing_service()` to inject `document_repository()`**

```python
def processing_service(self) -> ProcessingService:
    return ProcessingService(
        job_repo=self.job_repository(),
        artifact_repo=self.artifact_repository(),
        storage=self.storage_service(),
        parser=self.parser(),
        document_repo=self.document_repository(),
    )
```

- [ ] **Step 4: Lint + format**

```bash
ruff check . && ruff format .
```

- [ ] **Step 5: Commit**

```bash
git add worker/core/container.py
git commit -m "feat: wire document_repository and messaging_service in worker container"
```

---

## Task 4: Implement `RabbitMQConsumer`

The hottest file in this plan. Owns connection lifecycle, channel + queue setup, the consume loop, per-message dispatch, ack/retry, and graceful drain.

**Files:**
- Create: `worker/infrastructure/messaging/consumer.py`

- [ ] **Step 1: Define the class skeleton**

```python
class RabbitMQConsumer:
    def __init__(
        self,
        container: "Container",
        processing_service: ProcessingService,
        messaging: IMessagingService,
        job_repo: IJobRepository,
        url: str,
        queue: str,
    ) -> None: ...

    async def start(self) -> None: ...
    def request_stop(self) -> None: ...
```

Use a `TYPE_CHECKING` import for `Container` to avoid a circular import.

Internal state: `_stop_event: asyncio.Event`, `_in_flight: asyncio.Task | None = None`.

- [ ] **Step 2: Implement `start()` — connection and channel setup**

`start()` does roughly:

1. `connection = await aio_pika.connect_robust(self._url)`.
2. `async with connection:` so the connection closes when `start()` exits.
3. `channel = await connection.channel()`.
4. `await channel.set_qos(prefetch_count=1)`.
5. `queue = await channel.declare_queue(self._queue, durable=True)`.
6. Enter the consume loop (Step 3).
7. On exit, await any remaining `_in_flight` task before returning.

- [ ] **Step 3: Implement the consume loop**

Inside `start()`:

```python
async with queue.iterator() as it:
    async for msg in it:
        if self._stop_event.is_set():
            break
        self._in_flight = asyncio.create_task(self._handle(msg))
        await asyncio.shield(self._in_flight)
        self._in_flight = None
```

The `shield` keeps the handler from being cancelled mid-work if the iterator's enclosing task is cancelled. The `_stop_event` check before dispatching a new message is what enables drain (Section 6 of the spec).

`request_stop()` is just:

```python
def request_stop(self) -> None:
    self._stop_event.set()
```

It must be safe to call from a signal handler — `asyncio.Event.set()` is.

- [ ] **Step 4: Implement `_handle(msg)` — the per-message dispatcher**

Pseudocode for the handler:

```
try:
    payload = json.loads(msg.body)
    job_id = payload["job_id"]
except (json.JSONDecodeError, KeyError, TypeError):
    log warning "poison message dropped"
    await msg.ack()
    return

async with self._container.open_session() as session:
    job = await self._job_repo.get_for_processing(session, job_id)
    if job is None:
        log warning "job not found, dropping"
        await msg.ack()
        return
    if job.status is not JobStatus.QUEUED:
        log info "job not in QUEUED state ({job.status}), dropping (idempotency)"
        await msg.ack()
        return

# STARTED transition in its own session so it's committed before processing
async with self._container.open_session() as session:
    try:
        started = await self._job_repo.update_status(
            session, job_id, JobStatus.STARTED
        )
    except DatabaseException:
        log warning "could not mark started, requeue"
        await msg.nack(requeue=True)
        return

# Processing in its own session
try:
    async with self._container.open_session() as session:
        await self._processing_service.process(session, job_id)
    await msg.ack()
except Exception as e:
    await self._handle_failure(job_id, started.attempts, started.max_attempts, e)
    await msg.ack()
```

Notes:
- Three separate sessions: the status check, the STARTED transition, and the processing transaction. Each commits independently so a redelivery during processing sees STARTED in the DB (and gets idempotency-dropped).
- The retry path always acks the original message — re-enqueue is via `IMessagingService.enqueue`, not RabbitMQ redelivery.
- Catch broad `Exception` from the processing call. Per the spec, all exceptions inside `process` are retryable.

- [ ] **Step 5: Implement `_handle_failure(job_id, attempts, max_attempts, exc)`**

```
if attempts < max_attempts:
    async with self._container.open_session() as session:
        await self._job_repo.update_status(
            session, job_id, JobStatus.QUEUED, error_message=str(exc)
        )
    try:
        await self._messaging.enqueue(self._queue, {"job_id": job_id})
    except QueueException:
        log error "re-enqueue failed; job stranded in QUEUED"
        # ack still happens in the caller — stale-QUEUED sweeper is future work
else:
    async with self._container.open_session() as session:
        await self._job_repo.update_status(
            session, job_id, JobStatus.FAILED, error_message=str(exc)
        )
```

Note: `update_status` already stamps `failed_at` when status is `FAILED` (see the `_STATUS_TIMESTAMP` table in the existing repo).

- [ ] **Step 6: Lint + format**

```bash
ruff check . && ruff format .
```

- [ ] **Step 7: Commit**

```bash
git add worker/infrastructure/messaging/consumer.py
git commit -m "feat: implement RabbitMQConsumer"
```

---

## Task 5: Add `consumer()` factory to the container

**Files:**
- Modify: `worker/core/container.py`

- [ ] **Step 1: Add `consumer()` factory**

```python
def consumer(self) -> RabbitMQConsumer:
    return RabbitMQConsumer(
        container=self,
        processing_service=self.processing_service(),
        messaging=self.messaging_service(),
        job_repo=self.job_repository(),
        url=self._settings.rabbitmq_url,
        queue=self._settings.rabbitmq_queue,
    )
```

- [ ] **Step 2: Lint + format**

```bash
ruff check . && ruff format .
```

- [ ] **Step 3: Commit**

```bash
git add worker/core/container.py
git commit -m "feat: wire consumer factory in worker container"
```

---

## Task 6: Implement `worker/main.py` entry point

**Files:**
- Create: `worker/main.py`

- [ ] **Step 1: Write the entry point**

```python
import asyncio
import signal

from worker.core.container import container


async def _run() -> None:
    consumer = container.consumer()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, consumer.request_stop)
    await consumer.start()


if __name__ == "__main__":
    asyncio.run(_run())
```

- [ ] **Step 2: Lint + format**

```bash
ruff check . && ruff format .
```

- [ ] **Step 3: Commit**

```bash
git add worker/main.py
git commit -m "feat: add worker entry point"
```

---

## Task 7: End-to-end smoke test

The plan stops short of automated tests (deferred per project convention). This task is a manual smoke pass to confirm the wiring works.

**Files:**
- None modified.

- [ ] **Step 1: Bring the stack up**

```bash
docker compose up --build
```

Expect: api, worker, postgres, rabbitmq all running. Worker logs should show a connection to RabbitMQ and no immediate errors.

- [ ] **Step 2: Create a document, upload a small PDF, and create a job**

Using whichever client you prefer (`curl`, REST tab, etc.), exercise:

1. `POST /documents` → returns document id + presigned upload URL.
2. `PUT <presigned_url>` → upload a small PDF.
3. `POST /documents/{id}/process` → returns the new job. Worker should consume immediately.

Expect: job transitions `QUEUED → STARTED → COMPLETED`. Artifact row created. Markdown visible at the expected S3 key (`artifacts/{job_id}/{stem}.md`).

- [ ] **Step 3: Force a failure to exercise the retry path**

Quickest way: temporarily stop the S3 service (or hand the worker an unreachable bucket) and submit a job. Watch `attempts` increment in the `jobs` table on each retry, then transition to `FAILED` with a populated `error_message` and `failed_at` when `attempts == max_attempts`. Restore S3, submit a fresh job, confirm the happy path still works.

- [ ] **Step 4: Confirm graceful shutdown**

While a job is in flight, `docker compose kill -s SIGTERM worker` (or use Docker's stop). Worker should finish the in-flight job, ack, and exit. Check logs and the `jobs` row reflects `COMPLETED`.

- [ ] **Step 5: Commit any incidental fixes**

If anything came up during smoke testing, commit each fix on its own.

---

## Open Questions to Resolve During Implementation

- **Logger choice.** The plan calls for log lines on poison messages, drops, failures, and re-enqueue. No structured logger is in place yet; the worker can use `logging.getLogger(__name__)` for now. Revisit once the project picks a stdlib-vs-structlog direction.
- **`asyncio.shield` semantics.** Confirmed safe with `aio_pika`'s queue iterator pattern; if the iterator's context manager exits, the shielded task continues and is awaited explicitly before `start()` returns. If you hit cancellation surprises in practice, drop the `shield` and rely on the explicit `_in_flight` await — the trade-off is a marginally less clean cancel story.
