# Enqueue-After-Commit Fix

**Date:** 2026-05-13
**Branch:** `api/enqueue-before-commit-racecondition-36`

## Problem

RabbitMQ receives the job message before Postgres commits the job row. A fast consumer calls `get_for_processing`, finds `None` (the row is invisible under READ COMMITTED isolation), logs "job not found, dropping", and acks. The message is permanently lost, silently.

Root cause: `open_session` only commits after the route handler returns. `JobService.create` calls `messaging.enqueue()` mid-transaction, before any commit.

## Solution

Commit the job row before publishing to RabbitMQ. If enqueue subsequently fails, the job sits stranded in `QUEUED` — acceptable, covered by the planned stale-QUEUED sweeper.

## Design

### 1. Service layer — `JobService.create`

Remove the `update_status(QUEUED)` call. Add an explicit `session.commit()` after `repo.create` and before `enqueue`. Return the job DTO directly from `repo.create`.

```
create job as QUEUED (single insert)
await session.commit()        # row now visible to consumer
await messaging.enqueue(...)  # consumer will find QUEUED row
return job                    # open_session commit is a no-op
```

`expire_on_commit=False` is already set on the session factory, so the returned DTO remains valid after the explicit mid-method commit.

### 2. Repository layer — `JobRepository.create`

Change the INSERT to set `status=QUEUED` and `queued_at=now()` directly. Remove the hardcoded `status=JobStatus.CREATED`. No new method needed.

### 3. Migration

One Alembic revision covering four steps:

1. **Backfill** — update any existing `CREATED` rows to `QUEUED` with `queued_at=now()`
2. **Recreate enum** — create `job_status_enum_new` without `CREATED`, alter the column to cast to the new type, drop the old type, rename to `job_status_enum`
3. **Recreate partial index** — drop `one_active_job_per_document` and recreate it with only `QUEUED` and `STARTED` in the `WHERE` clause
4. **Update server_default** — change column `server_default` from `'CREATED'` to `'QUEUED'`

Downgrade reverses all four steps.

### 4. DTO / Python enum

- Remove `CREATED` from `JobStatus` in `shared/dtos/job.py`
- Update `shared/infrastructure/models.py`: change `default=JobStatus.CREATED` and `server_default="CREATED"` to `QUEUED`

## Failure modes

| Failure point | Outcome |
|---|---|
| `repo.create` fails | Transaction rolls back, nothing committed, no message sent. Clean. |
| `session.commit()` fails | Row not committed, no message sent. Clean. |
| `messaging.enqueue()` fails | Row committed as `QUEUED`, no message in queue. Job stranded — future sweeper recovers. |

## Files touched

- `api/services/job.py`
- `shared/infrastructure/repositories/job.py`
- `shared/dtos/job.py`
- `shared/infrastructure/models.py`
- `shared/migrations/versions/<new_revision>.py`
