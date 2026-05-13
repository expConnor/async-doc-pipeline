# Enqueue-After-Commit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix a race condition where RabbitMQ receives the job message before Postgres commits the job row, causing a fast consumer to find `None` and silently drop the message.

**Architecture:** Collapse the two-step CREATED→QUEUED insert into a single QUEUED insert, call `session.commit()` explicitly before `messaging.enqueue()`, and remove the now-dead `CREATED` status from both the Python enum and the Postgres enum type via a migration.

**Tech Stack:** FastAPI, SQLAlchemy 2.x async, aio_pika (RabbitMQ), Alembic, PostgreSQL

---

## Files

| Action | Path | What changes |
|--------|------|--------------|
| Modify | `shared/dtos/job.py` | Remove `CREATED` from `JobStatus` |
| Modify | `shared/infrastructure/models.py` | Update `default` and `server_default` from CREATED to QUEUED |
| Modify | `shared/infrastructure/repositories/job.py` | Insert with `status=QUEUED` and `queued_at=now()` |
| Modify | `api/services/job.py` | Remove `update_status(QUEUED)` call; add `session.commit()` before enqueue |
| Create | `shared/migrations/versions/<rev>_remove_created_from_job_status_enum.py` | Backfill, recreate enum, recreate index, update server_default |

---

### Task 1: Remove CREATED from Python enum and update model defaults

**Files:**
- Modify: `shared/dtos/job.py`
- Modify: `shared/infrastructure/models.py`

- [ ] **Step 1: Remove `CREATED` from `JobStatus` in `shared/dtos/job.py`**

  Replace the full enum:

  ```python
  class JobStatus(str, Enum):
      QUEUED = "queued"      # Job record exists and is enqueued
      STARTED = "started"    # Worker picked up job
      COMPLETED = "completed"
      FAILED = "failed"
  ```

- [ ] **Step 2: Update model defaults in `shared/infrastructure/models.py`**

  Change the `status` column definition (lines 45–50) to:

  ```python
  status: Mapped[JobStatus] = mapped_column(
      SQLEnum(JobStatus, name="job_status_enum"),
      default=JobStatus.QUEUED,
      server_default="QUEUED",
      nullable=False,
  )
  ```

- [ ] **Step 3: Lint**

  ```bash
  ruff check shared/dtos/job.py shared/infrastructure/models.py
  ```

  Expected: no errors.

- [ ] **Step 4: Commit**

  ```bash
  git add shared/dtos/job.py shared/infrastructure/models.py
  git commit -m "refactor: remove CREATED from JobStatus enum and update model defaults"
  ```

---

### Task 2: Update `JobRepository.create` to insert directly as QUEUED

**Files:**
- Modify: `shared/infrastructure/repositories/job.py`

- [ ] **Step 1: Update the INSERT in `JobRepository.create`**

  Replace the `.values(...)` block (lines 24–32) so the row is born as `QUEUED` with `queued_at` set:

  ```python
  query = (
      insert(Job)
      .values(
          account_id=dto.account_id,
          document_id=dto.document_id,
          artifact_types=dto.artifact_types,
          status=JobStatus.QUEUED,
          queued_at=datetime.now(),
          created_at=datetime.now(),
      )
      .returning(Job)
  )
  ```

- [ ] **Step 2: Lint**

  ```bash
  ruff check shared/infrastructure/repositories/job.py
  ```

  Expected: no errors.

- [ ] **Step 3: Commit**

  ```bash
  git add shared/infrastructure/repositories/job.py
  git commit -m "fix: insert job directly as QUEUED with queued_at timestamp"
  ```

---

### Task 3: Update `JobService.create` to commit before enqueue

**Files:**
- Modify: `api/services/job.py`

- [ ] **Step 1: Rewrite `JobService.create`**

  Remove the `update_status` call, add `session.commit()` before enqueue, return `job` from `repo.create`. Also remove `JobStatus` from the import since it is no longer used here.

  New imports line (line 10):
  ```python
  from shared.dtos.job import CreateJobDTO, JobDTO
  ```

  New `create` method (replacing lines 40–62):
  ```python
  async def create(self, session: Any, dto: CreateJobDTO) -> JobDTO:
      document = await self._document_repo.get_by_id(
          session, dto.document_id, dto.account_id
      )
      if document is None:
          raise DocumentNotFoundException()
      if not await self._storage.object_exists(document.object_key):
          raise DocumentNotUploadedException()

      depth = await self._messaging.queue_depth(self._queue)
      if depth >= self._backpressure_threshold:
          raise BackpressureException()

      job = await self._repo.create(session, dto)
      await session.commit()
      await self._messaging.enqueue(
          self._queue,
          {
              "job_id": job.id,
              "document_id": job.document_id,
              "artifact_types": [t.value for t in job.artifact_types],
          },
      )
      return job
  ```

- [ ] **Step 2: Lint**

  ```bash
  ruff check api/services/job.py
  ```

  Expected: no errors.

- [ ] **Step 3: Commit**

  ```bash
  git add api/services/job.py
  git commit -m "fix: commit job row before enqueue to eliminate consumer race condition"
  ```

---

### Task 4: Write Alembic migration to remove CREATED from the DB enum

**Files:**
- Create: `shared/migrations/versions/<rev>_remove_created_from_job_status_enum.py`

- [ ] **Step 1: Generate the migration file**

  From the project root:
  ```bash
  alembic revision -m "remove_created_from_job_status_enum"
  ```

  This creates `shared/migrations/versions/<rev>_remove_created_from_job_status_enum.py`. Open it.

- [ ] **Step 2: Fill in `upgrade()`**

  ```python
  def upgrade() -> None:
      # Backfill any rows stranded in CREATED before this fix
      op.execute(
          "UPDATE jobs SET status = 'QUEUED', queued_at = NOW() WHERE status = 'CREATED'"
      )

      # Drop index before altering the enum type it references
      op.execute("DROP INDEX one_active_job_per_document")

      # Recreate the enum without CREATED
      op.execute(
          "CREATE TYPE job_status_enum_new AS ENUM ('QUEUED', 'STARTED', 'COMPLETED', 'FAILED')"
      )
      op.execute(
          "ALTER TABLE jobs ALTER COLUMN status TYPE job_status_enum_new "
          "USING status::text::job_status_enum_new"
      )
      op.execute("DROP TYPE job_status_enum")
      op.execute("ALTER TYPE job_status_enum_new RENAME TO job_status_enum")

      # Recreate the partial unique index without CREATED
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

      # Update the column server_default
      op.execute(
          "ALTER TABLE jobs ALTER COLUMN status SET DEFAULT 'QUEUED'::job_status_enum"
      )
  ```

- [ ] **Step 3: Fill in `downgrade()`**

  ```python
  def downgrade() -> None:
      # Drop index before altering the enum type it references
      op.execute("DROP INDEX one_active_job_per_document")

      # Recreate enum with CREATED — must happen before setting CREATED as default
      op.execute(
          "CREATE TYPE job_status_enum_old AS ENUM ('CREATED', 'QUEUED', 'STARTED', 'COMPLETED', 'FAILED')"
      )
      op.execute(
          "ALTER TABLE jobs ALTER COLUMN status TYPE job_status_enum_old "
          "USING status::text::job_status_enum_old"
      )
      op.execute("DROP TYPE job_status_enum")
      op.execute("ALTER TYPE job_status_enum_old RENAME TO job_status_enum")

      # Now CREATED exists in the enum — safe to set as default
      op.execute(
          "ALTER TABLE jobs ALTER COLUMN status SET DEFAULT 'CREATED'::job_status_enum"
      )

      # Restore partial index with CREATED
      op.execute(
          """
          CREATE UNIQUE INDEX one_active_job_per_document
          ON jobs (account_id, document_id)
          WHERE status IN (
              'CREATED'::job_status_enum,
              'QUEUED'::job_status_enum,
              'STARTED'::job_status_enum
          )
          """
      )
  ```

- [ ] **Step 4: Set `down_revision`**

  The `down_revision` field in the generated file must point to the previous head. Check with:
  ```bash
  alembic heads
  ```
  The generated file will already have this set correctly if you ran `alembic revision` against a clean head.

- [ ] **Step 5: Apply and verify**

  Start the database (if not already running):
  ```bash
  docker compose up -d postgres
  ```

  Run the migration:
  ```bash
  alembic upgrade head
  ```

  Expected output: migration applies without error.

  Verify the enum no longer contains CREATED:
  ```bash
  docker compose exec postgres psql -U postgres -d doc-pipeline-db -c "\dT+ job_status_enum"
  ```

  Expected: enum values are `QUEUED`, `STARTED`, `COMPLETED`, `FAILED` — no `CREATED`.

- [ ] **Step 6: Commit**

  ```bash
  git add shared/migrations/versions/<rev>_remove_created_from_job_status_enum.py
  git commit -m "feat: migration to remove CREATED from job_status_enum"
  ```
