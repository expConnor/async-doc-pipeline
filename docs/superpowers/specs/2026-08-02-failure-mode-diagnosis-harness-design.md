# Failure-mode diagnosis harness

## Purpose

Find out what the pipeline actually does when things go wrong, rather than
what `CLAUDE.md` claims it does.

This spec covers **the harness skeleton plus specifications for all twelve
failure-mode scenarios**. The skeleton is built in one pass; each scenario is
then implemented independently, one per session. Every scenario spec below is
therefore written to be picked up cold — it states what is claimed, how to
inject the fault, what to record, and what is expected — without needing the
conversation that produced it.

This round is **diagnosis only**. No production code changes, no fixes. Fixes
become a separate, better-informed round once the findings exist.

Alongside the harness, `local/` is restructured from three loose files into a
small package, because the scenarios need the same submit → upload → process →
poll flow the smoke test already implements.

## Why not OpenTelemetry first

Considered and rejected for this round. OTel and a tracing UI answer "across
thousands of requests, where is time going?" — an aggregate question. These
scenarios run one at a time and ask a yes/no question about a single job, for
which better instruments already exist:

- The `jobs` table is a durable record of exactly what happened (`status`,
  `attempts`, the four lifecycle timestamps, `error_message`).
- structlog already emits the exact decision points under test
  (`consumer.idempotency_drop`, `consumer.job_failed_requeued`,
  `consumer.job_terminal_failure`, `consumer.concurrent_claim_dropped`).
- RabbitMQ's management UI already exposes queue depth, unacked count, and
  consumer count.

Traces are also actively *worse* for the top scenario: a SIGKILLed worker never
flushes its spans, whereas the job row survives. OTel belongs in a later round,
when sustained load on AWS needs aggregate latency breakdowns.

## Findings already established from code review

Recorded so scenarios can confirm or refute them — not so they are assumed
true.

**Hard-killed workers strand jobs in `STARTED` (expected real gap).**
`worker/infrastructure/messaging/consumer.py` drops any redelivered message
whose job is not `QUEUED`:

```python
if job.status is not JobStatus.QUEUED:
    logger.info("consumer.idempotency_drop", job_status=job.status.value)
    await msg.ack()
    return
```

A `SIGKILL` mid-job leaves the job in `STARTED`. RabbitMQ redelivers, the next
worker sees `STARTED`, acks and drops. There is no lease expiry, heartbeat, or
reaper, so the job is stuck permanently.

**No per-job timeout (expected real gap).** Nothing wraps
`ProcessingService.process()` in `asyncio.wait_for`. A pathological document
wedges that worker indefinitely, and since workers are the only scaling lever,
that is silent permanent capacity loss.

**The redelivery race looks sound (expected to pass).**
`shared/infrastructure/repositories/job.py` performs an atomic compare-and-swap
in SQL:

```python
update(Job).where(Job.id == job_id, Job.status == expected_status)
           .values(**values).returning(Job)
```

The database enforces the transition; a racing loser gets zero rows and raises
`JobStateConflictException`.

**Graceful shutdown may hang when idle (unknown).** `worker/main.py` binds
SIGTERM to `consumer.request_stop()`, which sets an `asyncio.Event`. The
consume loop only checks that event when the *next* message arrives:

```python
async for msg in it:
    if self._stop_event.is_set():
        break
```

An idle worker is blocked awaiting a message that may never come, so it may
never exit gracefully and would be SIGKILLed after Docker's grace period.

## Timing: the enabler

Landing a fault "mid-job" requires the job to actually be in `STARTED` when the
fault fires. With `local/sample.pdf` (3 pages) that window is ~3 seconds — too
tight to hit reliably.

Parse time is linear at ~1.0s per page on a 1-CPU worker (measured: 3pp/3.10s,
6pp/6.29s, 15pp/14.89s, 30pp/30.61s, 60pp/60.39s). A generated 60-page fixture
gives a ~60-second window, making every mid-job injection trivially reliable.
This is why fixture generation is part of the harness rather than an
afterthought.

Workers are capped at `cpus: 1` in `docker-compose.yml`, so this timing holds
regardless of replica count.

## Environment facts the scenarios rely on

- Compose network: `doc-pipeline_default`
- Queue name: `jobs` (`rabbitmq_queue` setting)
- Containers: `doc-pipeline-api`, `doc-pipeline-postgres`,
  `doc-pipeline-rabbitmq`, `doc-pipeline-minio`; workers are scaled replicas
  named `doc-pipeline-worker-N`, so they must be discovered at runtime, never
  hardcoded.
- `backpressure_threshold` defaults to 1000 and is env-settable.
- Backpressure is checked in `api/services/job.py` as `depth >= threshold`,
  *before* the job row is created, and raises `BackpressureException` → 429.
- Default worker replica count for scenarios is 3, which is required for the
  concurrency-dependent ones.

## Structure

```
local/
├── README.md               # what each entry point does, how to run
├── pipeline/               # shared toolkit — no scenario knowledge
│   ├── __init__.py
│   ├── client.py           # PipelineClient: submit, upload, process, poll
│   ├── jobs.py             # JobSnapshot + DB reads
│   ├── docker.py           # fault injection + log/queue capture
│   └── fixtures.py         # PDF generation
├── scenarios/              # one module per failure mode
│   ├── __init__.py         # SCENARIOS registry (name → run callable)
│   ├── base.py             # Report dataclass + formatting
│   └── <one module per scenario, added incrementally>
├── smoke.py                # entry point (replaces smoke_test.py)
└── chaos.py                # entry point: dispatches to scenarios
```

Boundaries: `client.py` talks HTTP and knows nothing about Docker. `docker.py`
injects faults and knows nothing about jobs. `jobs.py` reads state and knows
nothing about scenarios. Scenarios compose all three and own no primitives.

## Module responsibilities

### `pipeline/client.py`

`PipelineClient` — an async context manager wrapping the API and the presigned
upload. Applies the MinIO DNS patch on enter and restores it on exit, replacing
the current import-time global mutation.

```python
async with PipelineClient() as client:
    doc = await client.submit_document()          # -> Document(id, upload_url)
    await client.upload(doc.upload_url, pdf_bytes)
    job_id = await client.start_processing(doc.id)
    result = await client.wait_for_completion(job_id, timeout=...)
```

`start_processing` must surface a 429 as a distinct, catchable outcome rather
than a generic HTTP error — scenario 5 depends on distinguishing "rejected by
backpressure" from "failed".

The MinIO hostname patch carries over unchanged in behaviour from
`smoke_test.py`: presigned URLs contain the literal hostname `minio`, which
does not resolve from the host, and the SigV4 signature covers the `Host`
header so a string replacement would break it. `socket.getaddrinfo` is patched
to redirect `minio` (both `str` and `bytes` forms) to `localhost`. The existing
explanatory comment moves with the code.

### `pipeline/jobs.py`

Reads job state directly from Postgres via
`docker compose exec -T postgres psql`, not the HTTP API, because diagnosis
needs `attempts`, `last_attempt_at`, `failed_at`, and `error_message`, which
the API response does not expose.

- `JobSnapshot` — frozen dataclass: `id`, `status`, `attempts`, `max_attempts`,
  `queued_at`, `started_at`, `completed_at`, `failed_at`, `error_message`.
- `snapshot(job_id) -> JobSnapshot`
- `wait_for_status(job_id, status, timeout) -> JobSnapshot` — polls until the
  job reaches a status, raising `TimeoutError` with the last snapshot attached.
- `watch(job_id, duration) -> list[JobSnapshot]` — samples at a fixed interval,
  returning every distinct state observed. This is how "did it ever recover?"
  is answered.
- `artifact_count(document_id) -> int` — for detecting duplicate writes.

### `pipeline/docker.py`

Thin, explicit wrappers over Docker commands. Covers every injection needed by
the twelve scenarios, so no scenario shells out on its own:

- `worker_containers() -> list[str]` — discovered, never hardcoded
- `kill(container)` — `docker kill -s SIGKILL`
- `stop(container, timeout)` — `docker stop -t <timeout>`
- `start(container)` / `restart(container)`
- `pause(container)` / `unpause(container)`
- `scale_workers(n)` — `docker compose up -d --scale worker=n`
- `disconnect(container)` / `connect(container)` — `docker network
  disconnect|connect doc-pipeline_default <container>`, for simulating
  connectivity blips without shutting a dependency down
- `logs(service, since) -> str`
- `queue_depth() -> int`, `unacked_count() -> int` — via `rabbitmqctl
  list_queues name messages messages_unacknowledged`
- `container_state(container) -> ContainerState` — running flag, started-at,
  restart count, exit code; used to detect a worker process dying outright

Every mutating call must be reversible, and scenarios are responsible for
restoring the stack (reconnect networks, unpause, rescale) in a `finally`.

### `pipeline/fixtures.py`

Generates fixtures on demand into `local/fixtures/`, from the committed
`local/sample.pdf`:

- `slow_pdf()` — 60-page PDF (~60s parse), built by repeated `insert_pdf`
- `garbage_pdf()` — non-PDF bytes with a `.pdf` name

Fixtures are regenerated if missing and are gitignored, keeping ~1MB of binary
out of git history and preventing drift from the source sample.

### `scenarios/base.py`

`Report` — a dataclass holding the scenario name, an ordered list of
`(timestamp, event, detail)` observations, and a free-text `summary`. Renders
as a plain-text timeline.

Also defines the scenario contract every module implements:

```python
async def run(ctx: ScenarioContext) -> Report
```

`ScenarioContext` bundles the client, fixtures, and docker/jobs helpers so
scenario modules import one thing.

**No assertions anywhere.** For several scenarios the correct behaviour is not
yet known, and some are expected to misbehave; asserting would encode today's
guesses as requirements. Scenarios report; the human judges.

## Scenario specifications

Each becomes one module in `local/scenarios/`, registered by name in
`scenarios/__init__.py`, implemented in its own session. All assume 3 workers
unless stated otherwise, and all must restore the stack afterwards.

### 1. `worker-kill` — hard kill mid-job

*Claimed:* redelivery plus the idempotency check recovers the job.

Submit `slow.pdf`, `wait_for_status(STARTED)`, identify the claiming worker
from its logs, `kill()` it, then `watch()` for 60s.

Record: final job status and `attempts`; whether any surviving worker logged
`consumer.idempotency_drop`; queue depth over time; whether the job ever
reaches a terminal state.

*Expected:* real gap — job stranded in `STARTED` forever.

### 2. `shutdown-compare` — graceful vs. hard

*Claimed:* SIGTERM lets the in-flight job finish and ack; SIGKILL does not.

Three cases, reported side by side:

1. `stop(worker, timeout=90)` while a job is in flight. The 90s matters —
   Docker's default 10s grace is shorter than the 60s parse, so a default
   `docker stop` would SIGKILL mid-parse and prove nothing.
2. `kill(worker)` while a job is in flight.
3. SIGTERM to an **idle** worker — the suspected hang.

Record: shutdown duration, container exit code (137 indicates SIGKILL, so a
"graceful" stop exiting 137 was not graceful), final job status per case.

*Expected:* case 1 clean; case 2 stranded like scenario 1; case 3 unknown,
possibly hangs until the grace period expires.

### 3. `rabbitmq-restart` — broker restart mid-processing

*Claimed:* `aio_pika.connect_robust` reconnects.

Submit `slow.pdf`, wait for `STARTED`, then `restart(doc-pipeline-rabbitmq)`.
Hold until the broker is healthy again, then watch for 90s.

Record: whether workers reconnect (log evidence and consumer count on the
queue), what happens to the unacked in-flight message, whether the job
completes, is redelivered and dropped, or is stranded; final queue depth.

*Expected:* unknown. Reconnection likely works; the fate of the in-flight
message is the real question, and if it is redelivered while the job is
`STARTED` it will hit the same idempotency-drop hole as scenario 1.

### 4. `postgres-drop` — DB connectivity lost mid-job

*Claimed:* nothing specific. Open question.

Submit `slow.pdf`, wait for `STARTED`, then `disconnect(doc-pipeline-postgres)`
so the DB becomes unreachable without shutting down. Hold ~20s, then
`connect()` it again.

Record: whether the worker process survives or exits; whether it retries;
whether the exception escapes `_handle` — note that `_handle_failure` itself
opens a session, so a DB outage during failure handling can raise
`DatabaseException` before `msg.ack()` is reached, which may crash the consume
loop. Capture worker `container_state` before and after.

*Expected:* unknown, and this is the most likely place to find an unhandled
crash path.

### 5. `backpressure` — threshold exhaustion

*Claimed:* the API rejects new `/process` calls with 429 once queue depth
reaches `backpressure_threshold`.

Rather than queuing 1000 jobs, restart the API with a low threshold
(`BACKPRESSURE_THRESHOLD=5`) and scale workers to 0 so the queue cannot drain.
Submit documents until the API starts refusing.

Record: the depth at which the first 429 appears (should be exactly the
threshold, since the check is `>=`), whether any job row is created for a
rejected request (it should not be — the check precedes `create`), and that
requests succeed again once workers are scaled back up and the queue drains.

*Prerequisites:* API restarted with the env override; workers scaled to 0.
Both must be restored afterwards.

*Expected:* passes.

### 6. `corrupt-pdf` — malformed input, fault isolation

*Claimed:* one job per container isolates faults.

Upload `garbage.pdf` bytes to a presigned URL, then process. The question is
not whether the job fails — it is whether the **worker process survives**.
PyMuPDF is a C library; a segfault kills the container rather than raising a
catchable Python exception.

Record: status progression across retries, final `error_message`, whether the
job reaches terminal `FAILED` at `max_attempts`, and worker `container_state`
(uptime, restart count, exit code) before vs. after.

*Expected:* likely clean — `process()` raises, `except Exception` catches it.
The container-survival check is the real value.

### 7. `max-attempts` — retry exhaustion is terminal

*Claimed:* on failure, requeue while `attempts < max_attempts`, then terminal
`FAILED`; retrying jobs cycle through `QUEUED` and never touch `FAILED`.

Reuses the corrupt-PDF fixture as a deterministic failure, but focuses on the
retry ledger rather than process survival. Watch the job through every attempt.

Record: the full sequence of observed statuses (expect
`QUEUED → STARTED → QUEUED → … → FAILED`), `attempts` at each step, that
`failed_at` is written only on terminal failure, and that no further
redelivery occurs after `FAILED`.

*Expected:* passes.

### 8. `redelivery-race` — concurrent claims

*Claimed:* "the `STARTED` transition commits in its own session so a concurrent
redelivery sees it and drops."

With 3 workers live, publish the *same* `job_id` message to the queue N times
in rapid succession, forcing simultaneous claims.

Record: count of `consumer.job_started` log lines (must be exactly 1), count of
`concurrent_claim_dropped` / `idempotency_drop`, final `attempts`, and
`artifact_count(document_id)`. More than one `job_started`, or more than one
artifact row, means the compare-and-swap leaks.

*Expected:* passes, per the SQL compare-and-swap noted above. Worth proving
because the failure mode is silent.

### 9. `storage-down` — S3/MinIO unreachable mid-job

*Claimed:* nothing specific. Open question.

Two variants, since the worker touches storage twice:

1. `disconnect(doc-pipeline-minio)` before the fetch, so `get_object` fails.
2. `disconnect()` during the parse, so the *upload* fails after expensive work
   is already done.

Reconnect after ~20s in both.

Record: which exception surfaces, whether it is retried, whether the job lands
in `FAILED` cleanly or crashes the worker, and — for variant 2 — whether an
artifact row is created without a corresponding S3 object (silent data loss).

*Expected:* unknown. Variant 2 is the higher-value case.

### 10. `slow-pdf` — no per-job timeout

*Claimed:* nothing. This tests an absence.

Two parts. First, submit `slow.pdf` and measure whether anything ever
interrupts a 60-second parse. Second, `pause()` the worker mid-parse to
simulate a permanently wedged process, hold it, and observe whether the job is
ever reclaimed by another worker or whether that capacity is silently lost;
then `unpause()`.

Record: elapsed processing time, whether any timeout fired, job status while
paused and after unpause, queue depth throughout, and whether the paused
worker still counts as a live consumer on the queue.

*Expected:* real gap — no timeout exists; a paused worker holds its job
indefinitely.

### 11. `double-process` — same document, two jobs

*Claimed:* nothing directly, but object keys are deterministic per document, so
two jobs for one document write the same S3 key.

Submit one document, then call `/process` on it twice in quick succession to
create two distinct jobs racing on the same document.

Record: whether the API permits a second job while the first is active, whether
both jobs run to `COMPLETED`, how many artifact rows exist for the document,
and whether the artifact object is written twice.

*Expected:* likely both succeed and both write the same key — last write wins.
Distinguish harmless idempotent rewrite (same bytes) from genuine corruption
(interleaved writes, or two artifact rows pointing at one object).

### 12. `backlog-recovery` — deploy simulation

*Claimed:* nothing directly; this is the everyday case.

`scale_workers(0)`, submit ~20 documents so they queue with no consumers,
confirm depth, then `scale_workers(3)` and watch recovery.

Record: queue depth over time, whether every job eventually completes, whether
any job is lost or duplicated, time to drain, and whether jobs queued while
workers were absent show abnormal `attempts` counts.

*Expected:* passes. Worth confirming because it is the most frequently
exercised path in production.

## Build order

**This round:** everything under `pipeline/`, `scenarios/base.py`,
`scenarios/__init__.py` with an empty-but-working registry, `chaos.py`,
`smoke.py`, the README, and the supporting changes below.

Plus **one reference scenario, `worker-kill`**. A framework with no consumer
cannot be verified, and the first scenario is what proves the primitives are
the right shape. It also gives the remaining eleven sessions a concrete
template to copy. If it turns out the abstractions are wrong, that is far
cheaper to discover now than after eleven modules depend on them.

**Later rounds:** scenarios 2–12, one per session. Each adds exactly one module
plus one registry line, and touches nothing else.

## Smoke-test refactor

`local/smoke_test.py` becomes `local/smoke.py`, rebuilt on `PipelineClient`.
Behaviour is unchanged: `make run COUNT=12` works exactly as it does now.

Three concrete problems it fixes:

1. **Import-time global mutation.** The `socket.getaddrinfo` patch currently
   runs as a side effect of importing the module. It becomes explicit and
   scoped to `PipelineClient`'s lifetime.
2. **`_run_one` does five jobs at once** — submit, upload, process, poll,
   format, and error-handle in one ~50-line function, with a `queued_counter`
   threaded through solely for a progress message. It becomes short
   orchestration over the client's four methods.
3. **Results reporting tangled with execution.** `return False` loses *why* a
   run failed. A `Result` dataclass carries status, elapsed time, and error;
   the summary formats it.

## Supporting changes

**`Makefile`** — `run` points at `local/smoke.py`; one new target:

```
chaos:  ## Run a failure-injection scenario. Usage: make chaos SCENARIO=worker-kill
```

Bare `make chaos` lists available scenarios rather than erroring, matching the
existing convention that bare targets are safe.

**`.gitignore`** — currently `local/*` with explicit un-ignores for
`sample.pdf` and `smoke_test.py`. Updated to un-ignore `README.md`, `smoke.py`,
`chaos.py`, `pipeline/`, and `scenarios/`, while keeping `accounts.csv` and
`fixtures/` ignored.

**`local/README.md`** — what each entry point is for, how to run it, what each
scenario observes, and the scenario-adding checklist for future sessions.

## Out of scope

- **All fixes.** Diagnosis only.
- **Assertions and CI integration.** Once findings settle the real behaviour,
  confirmed guarantees get promoted into `tests/integration/` as proper pytest
  tests. Not before — several scenarios are expected to fail today.
- **OpenTelemetry**, per the reasoning above.

## Deliverable

A findings write-up covering, for each scenario: what `CLAUDE.md` claims, what
was actually observed, and whether that constitutes a gap. That document is the
input to the fix round.
