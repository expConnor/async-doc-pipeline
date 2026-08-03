from datetime import datetime
from uuid import UUID

import pytest
from pipeline.jobs import (
    _parse_row,
    artifact_count,
    snapshot,
    wait_for_status,
    watch,
)

JOB_ID = UUID("11111111-1111-1111-1111-111111111111")
DOC_ID = UUID("22222222-2222-2222-2222-222222222222")


def test_parse_row_handles_populated_and_null_fields():
    line = (
        f"{JOB_ID}|started|1|3|"
        "2026-08-03 10:00:00.000000|2026-08-03 10:00:01.500000||| "
    ).rstrip()
    # queued_at, started_at set; completed_at, failed_at, error_message empty
    line = (
        f"{JOB_ID}|started|1|3|2026-08-03 10:00:00.000000|"
        "2026-08-03 10:00:01.500000|||"
    )

    row = _parse_row(line)

    assert row.id == JOB_ID
    assert row.status == "started"
    assert row.attempts == 1
    assert row.max_attempts == 3
    assert row.queued_at == datetime.fromisoformat("2026-08-03 10:00:00.000000")
    assert row.started_at == datetime.fromisoformat(
        "2026-08-03 10:00:01.500000"
    )
    assert row.completed_at is None
    assert row.failed_at is None
    assert row.error_message is None


def test_snapshot_queries_and_parses(mocker):
    line = f"{JOB_ID}|queued|0|3|2026-08-03 10:00:00.000000||||"
    mocker.patch("pipeline.jobs._run_query", return_value=line + "\n")

    result = snapshot(JOB_ID)

    assert result.id == JOB_ID
    assert result.status == "queued"


def test_snapshot_raises_when_job_not_found(mocker):
    mocker.patch("pipeline.jobs._run_query", return_value="")

    with pytest.raises(ValueError):
        snapshot(JOB_ID)


def test_wait_for_status_polls_until_match(mocker):
    mocker.patch("pipeline.jobs.time.sleep")
    queued = _parse_row(f"{JOB_ID}|queued|0|3|||||")
    started = _parse_row(f"{JOB_ID}|started|1|3|||||")
    mocker.patch("pipeline.jobs.snapshot", side_effect=[queued, started])

    result = wait_for_status(JOB_ID, "started", timeout=5)

    assert result.status == "started"


def test_wait_for_status_times_out(mocker):
    mocker.patch("pipeline.jobs.time.sleep")
    queued = _parse_row(f"{JOB_ID}|queued|0|3|||||")
    mocker.patch("pipeline.jobs.snapshot", return_value=queued)
    mock_monotonic = mocker.patch("pipeline.jobs.time.monotonic")
    mock_monotonic.side_effect = [0, 0, 1, 2, 6]  # deadline computed at 0+5=5

    with pytest.raises(TimeoutError):
        wait_for_status(JOB_ID, "started", timeout=5)


def test_watch_collapses_consecutive_duplicate_statuses(mocker):
    mocker.patch("pipeline.jobs.time.sleep")
    started = _parse_row(f"{JOB_ID}|started|1|3|||||")
    failed = _parse_row(f"{JOB_ID}|failed|3|3|||||")
    mocker.patch(
        "pipeline.jobs.snapshot",
        side_effect=[started, started, failed, failed],
    )
    mock_monotonic = mocker.patch("pipeline.jobs.time.monotonic")
    mock_monotonic.side_effect = [0, 0, 1, 2, 3, 10]

    history = watch(JOB_ID, duration=4)

    assert [s.status for s in history] == ["started", "failed"]


def test_artifact_count_parses_integer(mocker):
    mocker.patch("pipeline.jobs._run_query", return_value="2\n")

    assert artifact_count(DOC_ID) == 2
