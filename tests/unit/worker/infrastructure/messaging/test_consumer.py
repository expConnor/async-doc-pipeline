from datetime import datetime
from uuid import UUID, uuid4

import pytest

from shared.core.exceptions import (
    DatabaseException,
    JobStateConflictException,
    QueueException,
)
from shared.dtos.artifact import ArtifactType
from shared.dtos.job import JobDTO, JobStatus

JOB_ID = UUID("018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e03")
DOCUMENT_ID = UUID("018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e01")
JOB_BODY = f'{{"job_id": "{JOB_ID}"}}'.encode()


@pytest.fixture
def processing_service(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def queued_job_dto():
    return JobDTO(
        id=JOB_ID,
        account_id=1,
        document_id=DOCUMENT_ID,
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
        id=JOB_ID,
        account_id=1,
        document_id=DOCUMENT_ID,
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
    # null JSON → job_id = None; UUID(str(None)) raises ValueError → poison
    msg.body = b'{"job_id": null}'

    await consumer._handle(msg)

    job_repo.get_for_processing.assert_not_called()
    msg.ack.assert_called_once()


async def test_handle_parses_job_id_as_uuid(consumer, msg, job_repo):
    job_id = uuid4()
    msg.body = f'{{"job_id": "{job_id}"}}'.encode()
    job_repo.get_for_processing.return_value = None

    await consumer._handle(msg)

    passed_id = job_repo.get_for_processing.await_args.args[1]
    assert passed_id == job_id
    assert isinstance(passed_id, UUID)


async def test_handle_malformed_uuid_acks_and_drops(consumer, msg, job_repo):
    msg.body = b'{"job_id": "not-a-uuid"}'

    await consumer._handle(msg)

    job_repo.get_for_processing.assert_not_called()
    msg.ack.assert_called_once()


async def test_handle_job_not_found_acks(consumer, msg, job_repo):
    msg.body = JOB_BODY
    job_repo.get_for_processing.return_value = None

    await consumer._handle(msg)

    msg.ack.assert_called_once()


async def test_handle_job_not_queued_acks(
    consumer, msg, job_repo, started_job_dto
):
    msg.body = JOB_BODY
    job_repo.get_for_processing.return_value = started_job_dto

    await consumer._handle(msg)

    job_repo.update_status.assert_not_called()
    msg.ack.assert_called_once()


async def test_handle_concurrent_claim_acks(
    consumer, msg, job_repo, queued_job_dto
):
    msg.body = JOB_BODY
    job_repo.get_for_processing.return_value = queued_job_dto
    job_repo.update_status.side_effect = JobStateConflictException()

    await consumer._handle(msg)

    msg.ack.assert_called_once()
    msg.nack.assert_not_called()


async def test_handle_started_db_error_nacks(
    consumer, msg, job_repo, queued_job_dto
):
    msg.body = JOB_BODY
    job_repo.get_for_processing.return_value = queued_job_dto
    job_repo.update_status.side_effect = DatabaseException()

    await consumer._handle(msg)

    msg.nack.assert_called_once_with(requeue=True)
    msg.ack.assert_not_called()


async def test_handle_open_session_raises_propagates(consumer, msg):
    msg.body = JOB_BODY
    consumer._container.open_session.side_effect = RuntimeError("db down")

    with pytest.raises(RuntimeError, match="db down"):
        await consumer._handle(msg)

    msg.ack.assert_not_called()
    msg.nack.assert_not_called()


async def test_handle_processing_success_acks(
    consumer, msg, job_repo, processing_service, queued_job_dto, started_job_dto
):
    msg.body = JOB_BODY
    job_repo.get_for_processing.return_value = queued_job_dto
    job_repo.update_status.return_value = started_job_dto

    await consumer._handle(msg)

    processing_service.process.assert_called_once()
    msg.ack.assert_called_once()
    msg.nack.assert_not_called()


async def test_handle_processing_failure_delegates(
    consumer,
    msg,
    job_repo,
    processing_service,
    queued_job_dto,
    started_job_dto,
    session,
):
    # started_job_dto has attempts=max_attempts=3, so _handle_failure takes the
    # terminal path (FAILED), keeping this test simple without chaining mocks.
    msg.body = JOB_BODY
    job_repo.get_for_processing.return_value = queued_job_dto
    job_repo.update_status.return_value = started_job_dto
    processing_service.process.side_effect = RuntimeError("processing failed")

    await consumer._handle(msg)

    job_repo.update_status.assert_called_with(
        session,
        JOB_ID,
        JobStatus.FAILED,
        expected_status=JobStatus.STARTED,
        error_message="processing failed",
    )
    msg.ack.assert_called_once()


async def test_failure_below_max_requeues(
    consumer, job_repo, messaging, session
):
    await consumer._handle_failure(JOB_ID, 1, 3, RuntimeError("failed"))

    job_repo.update_status.assert_called_once_with(
        session,
        JOB_ID,
        JobStatus.QUEUED,
        expected_status=JobStatus.STARTED,
        error_message="failed",
    )
    messaging.enqueue.assert_called_once_with("jobs", {"job_id": str(JOB_ID)})


async def test_failure_at_max_terminal(consumer, job_repo, messaging, session):
    await consumer._handle_failure(JOB_ID, 3, 3, RuntimeError("failed"))

    job_repo.update_status.assert_called_once_with(
        session,
        JOB_ID,
        JobStatus.FAILED,
        expected_status=JobStatus.STARTED,
        error_message="failed",
    )
    messaging.enqueue.assert_not_called()


async def test_failure_above_max_terminal(
    consumer, job_repo, messaging, session
):
    await consumer._handle_failure(JOB_ID, 4, 3, RuntimeError("failed"))

    job_repo.update_status.assert_called_once_with(
        session,
        JOB_ID,
        JobStatus.FAILED,
        expected_status=JobStatus.STARTED,
        error_message="failed",
    )
    messaging.enqueue.assert_not_called()


async def test_failure_reenqueue_queue_exception_logged(
    consumer, job_repo, messaging, session
):
    messaging.enqueue.side_effect = QueueException()

    await consumer._handle_failure(JOB_ID, 1, 3, RuntimeError("failed"))

    job_repo.update_status.assert_called_once_with(
        session,
        JOB_ID,
        JobStatus.QUEUED,
        expected_status=JobStatus.STARTED,
        error_message="failed",
    )
    # QueueException is caught and logged — no propagation


async def test_failure_update_failed_db_exception_propagates(
    consumer, job_repo
):
    job_repo.update_status.side_effect = DatabaseException()

    with pytest.raises(DatabaseException):
        await consumer._handle_failure(JOB_ID, 3, 3, RuntimeError("failed"))


async def test_failure_update_state_conflict_logged(consumer, job_repo):
    job_repo.update_status.side_effect = JobStateConflictException()

    # Caught by outer try/except — no propagation
    await consumer._handle_failure(JOB_ID, 3, 3, RuntimeError("failed"))
