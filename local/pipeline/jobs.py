"""Read job/artifact state straight from Postgres via psql in the postgres
container, bypassing the HTTP API. The API's JobResponse doesn't expose
attempts/last_attempt_at/failed_at/error_message together the way diagnosis
needs, and reading the DB directly is a durable record of exactly what
happened regardless of what the worker process is doing at the time.

All functions in this module are synchronous and block the calling thread
(`time.sleep` in `wait_for_status`/`watch`, `subprocess.run` in
`_run_query`). An `async def run(ctx)` scenario that needs to poll here
while also doing other async work (submitting more documents, driving the
API) must wrap these calls in `await asyncio.to_thread(...)` rather than
calling them directly, or the event loop will stall for the duration of
the poll/sleep.
"""

import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class JobSnapshot:
    id: UUID
    status: str
    attempts: int
    max_attempts: int
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    error_message: str | None


def _run_query(sql: str) -> str:
    # sh -c inside the container expands $POSTGRES_USER/$POSTGRES_DB from the
    # env_file docker-compose already gives the postgres service, so this
    # script never needs its own copy of those credentials.
    script = (
        f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A -F\'|\' -c "{sql}"'
    )
    cmd = ["docker", "compose", "exec", "-T", "postgres", "sh", "-c", script]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"command {cmd} failed (exit {e.returncode}): {e.stderr}"
        ) from e
    return result.stdout


def _parse_row(line: str) -> JobSnapshot:
    fields = line.split("|")

    def _dt(v: str) -> datetime | None:
        return datetime.fromisoformat(v) if v else None

    def _text(v: str) -> str | None:
        return v if v else None

    return JobSnapshot(
        id=UUID(fields[0]),
        status=fields[1].lower(),
        attempts=int(fields[2]),
        max_attempts=int(fields[3]),
        queued_at=_dt(fields[4]),
        started_at=_dt(fields[5]),
        completed_at=_dt(fields[6]),
        failed_at=_dt(fields[7]),
        error_message=_text(fields[8]),
    )


def snapshot(job_id: UUID) -> JobSnapshot:
    sql = (
        "SELECT id, status, attempts, max_attempts, queued_at, started_at, "
        "completed_at, failed_at, error_message FROM jobs WHERE id = "
        f"'{job_id}'"
    )
    out = _run_query(sql).strip()
    if not out:
        raise ValueError(f"job {job_id} not found")
    return _parse_row(out)


def wait_for_status(
    job_id: UUID, status: str, timeout: float, interval: float = 1.0
) -> JobSnapshot:
    # JobSnapshot.status is always lowercase (see _parse_row); normalize the
    # caller-supplied status the same way so e.g. "STARTED" (an easy mistake,
    # since the DB's raw enum labels are uppercase) matches instead of
    # silently polling until timeout.
    status = status.lower()
    deadline = time.monotonic() + timeout
    last = snapshot(job_id)
    while last.status != status and time.monotonic() < deadline:
        time.sleep(interval)
        last = snapshot(job_id)
    if last.status != status:
        raise TimeoutError(
            f"job {job_id} did not reach status={status!r}; last={last}"
        )
    return last


def watch(
    job_id: UUID, duration: float, interval: float = 1.0
) -> list[JobSnapshot]:
    deadline = time.monotonic() + duration
    seen: list[JobSnapshot] = []
    while time.monotonic() < deadline:
        snap = snapshot(job_id)
        if not seen or seen[-1].status != snap.status:
            seen.append(snap)
        time.sleep(interval)
    return seen


def artifact_count(document_id: UUID) -> int:
    sql = f"SELECT count(*) FROM artifacts WHERE document_id = '{document_id}'"
    return int(_run_query(sql).strip())
