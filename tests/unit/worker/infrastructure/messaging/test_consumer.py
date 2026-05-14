from datetime import datetime

import pytest

from shared.dtos.artifact import ArtifactType
from shared.dtos.job import JobDTO, JobStatus


@pytest.fixture
def processing_service(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def queued_job_dto():
    return JobDTO(
        id=10,
        account_id=1,
        document_id=1,
        status=JobStatus.QUEUED,
        artifact_types=[ArtifactType.MARKDOWN],
        attempts=1,
        max_attempts=3,
        error_message=None,
        created_at=datetime(2026, 1, 1),
        queued_at=datetime(2026, 1, 1),
        started_at=None,
        completed_at=None,
        last_attempt_at=None,
        failed_at=None,
    )


@pytest.fixture
def started_job_dto():
    # attempts == max_attempts: makes _handle_failure take the terminal path,
    # keeping failure-delegation tests deterministic without chaining mocks.
    return JobDTO(
        id=10,
        account_id=1,
        document_id=1,
        status=JobStatus.STARTED,
        artifact_types=[ArtifactType.MARKDOWN],
        attempts=3,
        max_attempts=3,
        error_message=None,
        created_at=datetime(2026, 1, 1),
        queued_at=datetime(2026, 1, 1),
        started_at=datetime(2026, 1, 1),
        completed_at=None,
        last_attempt_at=None,
        failed_at=None,
    )


@pytest.fixture
def msg(mocker):
    return mocker.AsyncMock()


async def test_handle_bad_json_acks(consumer, msg, job_repo):
    msg.body = b"not json"

    await consumer._handle(msg)

    msg.ack.assert_called_once()
    job_repo.get_for_processing.assert_not_called()


async def test_handle_missing_job_id_acks(consumer, msg, job_repo):
    msg.body = b'{"foo": 1}'

    await consumer._handle(msg)

    msg.ack.assert_called_once()
    job_repo.get_for_processing.assert_not_called()


async def test_handle_null_job_id_acks(consumer, msg, job_repo):
    # null JSON → job_id = None; code does not raise, falls to repo lookup
    msg.body = b'{"job_id": null}'
    job_repo.get_for_processing.return_value = None

    await consumer._handle(msg)

    assert job_repo.get_for_processing.call_args.args[1] is None
    msg.ack.assert_called_once()


async def test_handle_job_not_found_acks(consumer, msg, job_repo):
    msg.body = b'{"job_id": 10}'
    job_repo.get_for_processing.return_value = None

    await consumer._handle(msg)

    msg.ack.assert_called_once()


async def test_handle_job_not_queued_acks(
    consumer, msg, job_repo, started_job_dto
):
    msg.body = b'{"job_id": 10}'
    job_repo.get_for_processing.return_value = started_job_dto

    await consumer._handle(msg)

    job_repo.update_status.assert_not_called()
    msg.ack.assert_called_once()
