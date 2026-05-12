# Worker RabbitMQ Consumer Design

**Date:** 2026-05-12
**Branch:** `worker/implement-rabbitmq-consumer-32`

## Goal

Implement the worker's RabbitMQ consumer: the entry point that pulls job messages from the `jobs` queue, drives `ProcessingService` per message, and applies the DB-scoped retry policy defined in `CLAUDE.md`. After this work, the local `docker compose up` flow processes uploaded PDFs end-to-end without manual intervention.

In scope:

- `worker/infrastructure/messaging/consumer.py` — `RabbitMQConsumer`.
- `worker/main.py` — process entry point.
- A small refactor to `worker/services/processing_service.py` to take only `job_id` and resolve the document internally.
- New `mark_started` method on `IJobRepository` (atomic status + attempts + `last_attempt_at` write).
- DI wiring in `worker/core/container.py` for the new pieces (`document_repository`, `messaging_service`, `consumer`).

Out of scope:

- Backoff / delayed retries (deferred; see Future Work).
- Dead-letter queue (deferred; DB is source of truth for failures).
- Sweeper for stale `QUEUED` jobs (deferred; see Future Work).
- Idempotent re-processing of partial completions (deferred; see Future Work).

## Design Decisions

### 1. Concurrency: serial per worker process (`prefetch_count=1`)

One in-flight message at a time per worker container. Throughput scales by adding workers, matching the existing "scale on queue depth" model from `CLAUDE.md`. PDF parsing is CPU-bound and synchronous, so in-process parallelism (asyncio fan-out or a process pool) would add complexity without proportional gain at this stage. Revisit once load testing produces concrete numbers.

### 2. Document hydration: inside `ProcessingService`

`ProcessingService.process` is refactored from

```
process(session, job_id, document_id, object_key, file_name)
```

to

```
process(session, job_id)
```

The service loads the job (`IJobRepository.get_by_id` — or a worker-side variant that doesn't require `account_id`, see Open Questions) and the document (`IDocumentRepository`) itself. The consumer becomes a transport layer: parse JSON → hand off → ack/retry. The producer (API) keeps publishing the minimal payload `{job_id, document_id, artifact_types}` it already publishes; the worker only reads `job_id` from it.

Rejected alternative: denormalize `object_key` and `file_name` into the queue payload. This couples the API to whatever fields the worker happens to need today, freezes potentially-stale snapshots into messages, and saves no meaningful DB load given the worker already opens a session per job for status writes.

### 3. Retry policy: DB-scoped, all exceptions retryable, no backoff

All exceptions raised inside `ProcessingService.process` are treated as retryable.

```
if job.attempts < job.max_attempts:
    status=QUEUED, error_message=str(e), commit
    IMessagingService.enqueue(queue, {job_id})
    ack
else:
    status=FAILED, failed_at=now(), error_message=str(e), commit
    ack
```

`attempts` is incremented atomically with the `STARTED` transition (`mark_started`), so the comparison uses the post-increment value. With `max_attempts=3`: attempt 1 fails → `attempts=1`, retry. Attempt 3 fails → `attempts=3`, `3 < 3` false → terminal `FAILED`. `FAILED` is never re-visited by retrying jobs (CLAUDE.md guarantee); `failed_at` is only written on terminal failure.

Re-enqueue uses `IMessagingService.enqueue` directly, not RabbitMQ's `nack`/redelivery. The broker is a transport; the DB is the source of truth for retry state.

No backoff between retries. Immediate re-publish. If load testing shows attempts being burned on transient outages, this is the place to add a delayed-message exchange or TTL-DLX bounce queue (see Future Work).

No dead-letter queue. Terminal `FAILED` rows in the DB are the failure record. A DLQ would duplicate that data into the broker without giving operators anything they can't already query.

### 4. Failure classification

| Failure category                                                                            | Handling                                                                                                                                                                                                                                                                              |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Malformed JSON or missing `job_id` in payload                                               | Ack-drop with a log. Poison message; replaying it will fail the same way.                                                                                                                                                                                                             |
| `job_id` resolves to no row in DB                                                           | Ack-drop with a log. Same reasoning.                                                                                                                                                                                                                                                  |
| Job exists but status is `COMPLETED`, `FAILED`, or `STARTED`                                | Ack-drop. Idempotency on redelivery — another worker is on it or finished it already.                                                                                                                                                                                                 |
| Exception in `processing_service.process`                                                   | DB-scoped retry path (Section 3 above).                                                                                                                                                                                                                                               |
| DB exception during the `mark_started` transition                                           | Nack with `requeue=true`. Broker redelivers; when DB recovers, the next consume proceeds normally. `attempts` was not bumped (transaction rolled back).                                                                                                                               |
| Exception while writing the failure transition itself (DB or broker down during re-enqueue) | Log loudly. Ack if the DB write succeeded, nack otherwise. Worst-case outcome is a job stranded in `QUEUED` with no broker message — bounded operational issue, addressable by a future sweeper (see Future Work). Preferred over double-counting attempts via repeated redeliveries. |

### 5. Idempotency on redelivery

RabbitMQ provides at-least-once delivery. A worker that crashes between committing `COMPLETED` and acking will see the message redelivered. The consumer guards against this by reading the job's current status before doing any work: if it isn't `QUEUED`, the consumer acks and returns without entering processing. This makes redelivery safe and also handles the rare case where two workers somehow see the same message (e.g., during a broker partition).

### 6. Graceful shutdown

On `SIGTERM` or `SIGINT`, the consumer:

1. Sets an internal `asyncio.Event` (the stop signal).
2. Stops pulling new messages — exits the `queue.iterator()` loop.
3. Awaits the in-flight task (if any) to completion. The work is wrapped in `asyncio.shield` so the signal doesn't cancel it mid-flight.
4. Closes the channel and connection.
5. Returns from `start()`, letting `asyncio.run` exit cleanly.

If the in-flight job exceeds the ECS grace period (default ~30s, configurable), the container is SIGKILLed and the unacked message gets redelivered. The idempotency guard ack-drops the redelivery in both possible states: if the job had committed `COMPLETED`, that's the intended drop; if it was still `STARTED` (mid-processing when killed), the redelivery also drops to avoid double-processing in case the original worker isn't actually dead. The cost is that an interrupted job is stranded in `STARTED` until manual recovery or a stale-`STARTED` sweeper (see Future Work). For graceful drains within the grace period this never triggers — the worker acks normally on its way out.

## Components

### `RabbitMQConsumer`

`worker/infrastructure/messaging/consumer.py`. Owns the aio_pika connection lifecycle, channel + queue setup, the consume loop, per-message handling, and the shutdown drain. No business logic.

Dependencies (constructor):

- `container: Container` — for `open_session()`.
- `processing_service: ProcessingService` — for the work itself.
- `messaging: IMessagingService` — for re-enqueueing failed jobs.
- `job_repo: IJobRepository` — for status writes around processing.
- `url: str`, `queue: str` — from settings.

Surface:

- `async def start() -> None` — connect, set qos, declare queue, consume, drain on stop.
- `def request_stop() -> None` — sets the stop event; safe to call from a signal handler.

Channel setup: `set_qos(prefetch_count=1)`, `declare_queue(queue, durable=True)` (matches `RabbitMQMessagingService.enqueue` on the producer side).

### `ProcessingService` (refactor)

Signature change: `process(session, job_id)`. Inside, it:

1. Loads the job.
2. Loads the document via `IDocumentRepository`.
3. Sets `STARTED` (handled by the consumer before calling `process`; see Components → `RabbitMQConsumer`).
4. Fetches the PDF bytes from storage.
5. Runs the parser.
6. Uploads the markdown to S3.
7. Creates the artifact row.
8. Sets status to `COMPLETED`.

Steps 3 and 8 are status transitions. The consumer owns the `STARTED` transition (because that's where attempts are bumped and the idempotency-relevant commit happens) and the failure path. `ProcessingService` only owns the `COMPLETED` transition on the success path. This keeps retry mechanics centralized in the consumer.

### `IJobRepository.mark_started`

New method:

```
async def mark_started(session, job_id) -> JobDTO
```

Atomically: increment `attempts`, set `last_attempt_at = now()`, set `status = STARTED`. Returns the updated `JobDTO` so the consumer can read the post-increment `attempts` value when deciding retry-vs-fail later.

`update_status` stays as-is; we don't overload it.

### `worker/main.py`

Constructs the container, instantiates the consumer, registers signal handlers, and runs the event loop. Roughly:

```
async def _run():
    consumer = container.consumer()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, consumer.request_stop)
    await consumer.start()

if __name__ == "__main__":
    asyncio.run(_run())
```

### Container additions

`worker/core/container.py` gains:

- `document_repository() -> IDocumentRepository` — returns `DocumentRepository()`.
- `messaging_service() -> IMessagingService` — returns `RabbitMQMessagingService(url=settings.rabbitmq_url)`.
- `consumer() -> RabbitMQConsumer` — wires the consumer with `self`, `processing_service()`, `messaging_service()`, `job_repository()`, `settings.rabbitmq_url`, `settings.rabbitmq_queue`.

`processing_service()` is updated to inject `document_repository()` alongside the existing dependencies.

## End-to-end message flow

```
broker delivers message
  │
  ├─ JSON parse fails → log + ack + return
  │
  └─ parsed → {job_id}
       │
       ├─ open session
       │
       ├─ load job
       │    ├─ not found → log + ack + return
       │    └─ status != QUEUED → log + ack + return  (idempotency)
       │
       ├─ mark_started(job_id)  (commits: STARTED, attempts++, last_attempt_at)
       │    └─ DB exception → nack(requeue=true), log
       │
       ├─ processing_service.process(session, job_id)
       │    ├─ success → status=COMPLETED, commit, ack
       │    │
       │    └─ exception caught in consumer
       │         ├─ attempts < max_attempts:
       │         │     status=QUEUED, error_message, commit
       │         │     IMessagingService.enqueue(queue, {job_id})
       │         │     ack
       │         │
       │         └─ else:
       │               status=FAILED, failed_at, error_message, commit
       │               ack
```

## Open Questions

- **`IJobRepository.get_by_id` requires `account_id` today** (API-side authorization). The worker has no account context — it's the trusted processor. Either (a) add a worker-only `get_by_id(session, job_id)` overload, or (b) accept the parameter and pass `account_id` derived from the loaded job. (a) is cleaner; (b) avoids interface churn. Resolve during implementation, but lean towards (a).

## Future Work

- **Delayed retries** via the RabbitMQ delayed-message-exchange plugin or a TTL-DLX bounce queue. Worth adding once load testing shows attempts being burned on transient outages.
- **Stale-job sweeper.** Periodic job that finds (a) rows in `QUEUED` older than some threshold with no corresponding message in the broker, and (b) rows in `STARTED` older than some threshold (orphaned by SIGKILLed workers — see Section 6). Resets them to `QUEUED` and re-enqueues. Mitigates the bounded edge cases in failure category 6 and the shutdown-by-SIGKILL path.
- **Idempotent re-processing of partial completions.** Today, if a worker dies between writing markdown to S3 and committing `COMPLETED`, the markdown and possibly the artifact row are orphaned. A retry from scratch will produce a duplicate. Solving this means making the storage write and artifact creation idempotent (e.g., overwrite by deterministic key, upsert artifact). Defer until it shows up as a real problem.
- **Failure classification.** Once we have failure data, split transient infra errors (retry) from deterministic content errors (immediate `FAILED`) to avoid burning attempts on inputs that will never parse.
- **In-process concurrency.** Revisit `prefetch_count` and concurrent task fan-out if per-worker CPU utilization stays low under load.