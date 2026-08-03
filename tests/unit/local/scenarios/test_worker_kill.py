from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from pipeline.jobs import JobSnapshot
from scenarios.base import Report, ScenarioContext
from scenarios.worker_kill import run

DOC_ID = UUID("11111111-1111-1111-1111-111111111111")
JOB_ID = UUID("22222222-2222-2222-2222-222222222222")


def _snapshot(status: str, attempts: int = 1) -> JobSnapshot:
    return JobSnapshot(
        id=JOB_ID,
        status=status,
        attempts=attempts,
        max_attempts=3,
        queued_at=None,
        started_at=None,
        completed_at=None,
        failed_at=None,
        error_message=None,
    )


async def test_worker_kill_finds_and_kills_the_claiming_worker():
    client = AsyncMock()
    client.submit_document.return_value = SimpleNamespace(
        id=DOC_ID, upload_url="http://x/upload"
    )
    client.start_processing.return_value = JOB_ID

    jobs = MagicMock()
    jobs.wait_for_status.return_value = _snapshot("started")
    jobs.watch.return_value = [_snapshot("started"), _snapshot("started")]

    docker = MagicMock()
    docker.worker_containers.return_value = [
        "doc-pipeline-worker-1",
        "doc-pipeline-worker-2",
    ]
    docker.logs.return_value = (
        f"worker-1  | consumer.job_started job_id={JOB_ID}"
    )
    docker.queue_depth.return_value = 0
    docker.configured_worker_replicas.return_value = 3

    fixtures = MagicMock()
    fixtures.slow_pdf.return_value = SimpleNamespace(
        read_bytes=lambda: b"pdf-bytes"
    )

    ctx = ScenarioContext(
        client=client, fixtures=fixtures, docker=docker, jobs=jobs
    )

    report = await run(ctx)

    client.submit_document.assert_awaited_once()
    client.upload.assert_awaited_once_with("http://x/upload", b"pdf-bytes")
    client.start_processing.assert_awaited_once_with(DOC_ID)
    jobs.wait_for_status.assert_called_once_with(JOB_ID, "started", timeout=15)
    docker.kill.assert_called_once_with("doc-pipeline-worker-1")
    jobs.watch.assert_called_once_with(JOB_ID, duration=60)
    docker.scale_workers.assert_called_once_with(3)

    assert isinstance(report, Report)
    assert report.scenario == "worker-kill"
    assert "final_status=started" in report.summary
    event_names = [e[1] for e in report.events]
    assert event_names == [
        "submitted",
        "processing_started",
        "job_started",
        "claiming_worker_identified",
        "worker_killed",
        "status_observed",
        "status_observed",
        "final_queue_depth",
    ]


async def test_worker_kill_records_error_if_no_worker_log_matches():
    client = AsyncMock()
    client.submit_document.return_value = SimpleNamespace(
        id=DOC_ID, upload_url="http://x/upload"
    )
    client.start_processing.return_value = JOB_ID

    jobs = MagicMock()
    jobs.wait_for_status.return_value = _snapshot("started")

    docker = MagicMock()
    docker.worker_containers.return_value = ["doc-pipeline-worker-1"]
    docker.logs.return_value = "worker-1  | (nothing relevant)"
    docker.configured_worker_replicas.return_value = 3

    fixtures = MagicMock()
    fixtures.slow_pdf.return_value = SimpleNamespace(
        read_bytes=lambda: b"pdf-bytes"
    )

    ctx = ScenarioContext(
        client=client, fixtures=fixtures, docker=docker, jobs=jobs
    )

    # The lookup helper's RuntimeError must not propagate out of run(): it
    # is caught, recorded as a "scenario_error" event, and a Report is
    # still returned so chaos.py always has something to print.
    report = await run(ctx)

    assert isinstance(report, Report)
    event_names = [e[1] for e in report.events]
    assert event_names[-1] == "scenario_error"
    assert "no worker log line found" in report.events[-1][2]
    assert "scenario raised" in report.summary
    docker.kill.assert_not_called()
    docker.scale_workers.assert_called_once_with(3)


async def test_worker_kill_records_error_if_log_short_name_has_no_container():
    client = AsyncMock()
    client.submit_document.return_value = SimpleNamespace(
        id=DOC_ID, upload_url="http://x/upload"
    )
    client.start_processing.return_value = JOB_ID

    jobs = MagicMock()
    jobs.wait_for_status.return_value = _snapshot("started")

    docker = MagicMock()
    # The log line matches on job_id and "job_started", but its short name
    # ("worker-9") doesn't correspond to any real container in the list —
    # e.g. a stale/scaled-down replica. This must be recorded as an error,
    # not silently pass the unresolved short name straight to docker.kill().
    docker.worker_containers.return_value = ["doc-pipeline-worker-1"]
    docker.logs.return_value = (
        f"worker-9  | consumer.job_started job_id={JOB_ID}"
    )
    docker.configured_worker_replicas.return_value = 3

    fixtures = MagicMock()
    fixtures.slow_pdf.return_value = SimpleNamespace(
        read_bytes=lambda: b"pdf-bytes"
    )

    ctx = ScenarioContext(
        client=client, fixtures=fixtures, docker=docker, jobs=jobs
    )

    report = await run(ctx)

    assert isinstance(report, Report)
    event_names = [e[1] for e in report.events]
    assert event_names[-1] == "scenario_error"
    assert "no container" in report.events[-1][2]
    assert "scenario raised" in report.summary
    docker.kill.assert_not_called()
    docker.scale_workers.assert_called_once_with(3)
