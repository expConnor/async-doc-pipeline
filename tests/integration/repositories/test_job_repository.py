import pytest

from shared.core.exceptions import (
    ActiveJobExistsException,
    DatabaseException,
    JobStateConflictException,
)
from shared.dtos.artifact import ArtifactType
from shared.dtos.job import CreateJobDTO, JobStatus
from shared.infrastructure.repositories.job import JobRepository


@pytest.fixture
def repo():
    return JobRepository()


async def test_create_success(repo, db_session, account, document):
    dto = await repo.create(
        db_session,
        CreateJobDTO(
            account_id=account.id,
            document_id=document.id,
            artifact_types=[ArtifactType.MARKDOWN],
        ),
    )

    assert dto.id is not None
    assert dto.account_id == account.id
    assert dto.document_id == document.id
    assert dto.status == JobStatus.QUEUED
    assert dto.artifact_types == [ArtifactType.MARKDOWN]
    assert dto.attempts == 0
    assert dto.max_attempts == 3
    assert dto.error_message is None
    assert dto.created_at is not None
    assert dto.queued_at is not None
    assert dto.started_at is None
    assert dto.completed_at is None
    assert dto.last_attempt_at is None
    assert dto.failed_at is None


async def test_create_to_dto_field_completeness(
    repo, db_session, account, document
):
    dto = await repo.create(
        db_session,
        CreateJobDTO(
            account_id=account.id,
            document_id=document.id,
            artifact_types=[ArtifactType.MARKDOWN],
        ),
    )

    assert hasattr(dto, "id")
    assert hasattr(dto, "account_id")
    assert hasattr(dto, "document_id")
    assert hasattr(dto, "status")
    assert hasattr(dto, "artifact_types")
    assert hasattr(dto, "attempts")
    assert hasattr(dto, "max_attempts")
    assert hasattr(dto, "error_message")
    assert hasattr(dto, "created_at")
    assert hasattr(dto, "queued_at")
    assert hasattr(dto, "started_at")
    assert hasattr(dto, "completed_at")
    assert hasattr(dto, "last_attempt_at")
    assert hasattr(dto, "failed_at")


async def test_create_active_job_exists_raises(
    repo, db_session, account, document, job
):
    # `job` fixture already holds a QUEUED job for this document
    with pytest.raises(ActiveJobExistsException):
        await repo.create(
            db_session,
            CreateJobDTO(
                account_id=account.id,
                document_id=document.id,
                artifact_types=[ArtifactType.MARKDOWN],
            ),
        )


async def test_create_nonexistent_document_raises_database_exception(
    repo, db_session, account
):
    with pytest.raises(DatabaseException):
        await repo.create(
            db_session,
            CreateJobDTO(
                account_id=account.id,
                document_id=999999,
                artifact_types=[ArtifactType.MARKDOWN],
            ),
        )


async def test_get_by_id_matching_account(repo, db_session, account, job):
    dto = await repo.get_by_id(db_session, job.id, account.id)

    assert dto is not None
    assert dto.id == job.id
    assert dto.account_id == account.id


async def test_get_by_id_mismatched_account(repo, db_session, account_b, job):
    dto = await repo.get_by_id(db_session, job.id, account_b.id)

    assert dto is None


async def test_get_by_id_nonexistent(repo, db_session, account):
    dto = await repo.get_by_id(db_session, 999999, account.id)

    assert dto is None


async def test_get_for_processing_ignores_account(
    repo, db_session, account_b, job
):
    # get_for_processing has no account filter — returns job for any caller
    dto = await repo.get_for_processing(db_session, job.id)

    assert dto is not None
    assert dto.id == job.id


async def test_get_for_processing_nonexistent(repo, db_session):
    dto = await repo.get_for_processing(db_session, 999999)

    assert dto is None


async def test_update_status_queued_to_started(repo, db_session, job):
    dto = await repo.update_status(
        db_session,
        job.id,
        JobStatus.STARTED,
        expected_status=JobStatus.QUEUED,
    )

    assert dto.status == JobStatus.STARTED
    assert dto.started_at is not None
    assert dto.last_attempt_at is not None
    assert dto.attempts == 1


async def test_update_status_started_to_completed(repo, db_session, job):
    await repo.update_status(
        db_session,
        job.id,
        JobStatus.STARTED,
        expected_status=JobStatus.QUEUED,
    )
    dto = await repo.update_status(
        db_session,
        job.id,
        JobStatus.COMPLETED,
        expected_status=JobStatus.STARTED,
    )

    assert dto.status == JobStatus.COMPLETED
    assert dto.completed_at is not None


async def test_update_status_started_to_failed(repo, db_session, job):
    await repo.update_status(
        db_session,
        job.id,
        JobStatus.STARTED,
        expected_status=JobStatus.QUEUED,
    )
    dto = await repo.update_status(
        db_session,
        job.id,
        JobStatus.FAILED,
        expected_status=JobStatus.STARTED,
        error_message="something broke",
    )

    assert dto.status == JobStatus.FAILED
    assert dto.failed_at is not None
    assert dto.error_message == "something broke"


async def test_update_status_started_to_queued_retry(repo, db_session, job):
    await repo.update_status(
        db_session,
        job.id,
        JobStatus.STARTED,
        expected_status=JobStatus.QUEUED,
    )
    dto = await repo.update_status(
        db_session,
        job.id,
        JobStatus.QUEUED,
        expected_status=JobStatus.STARTED,
        error_message="transient error",
    )

    assert dto.status == JobStatus.QUEUED
    assert dto.queued_at is not None
    assert dto.error_message == "transient error"


async def test_update_status_wrong_expected_raises_conflict(
    repo, db_session, job
):
    with pytest.raises(JobStateConflictException):
        await repo.update_status(
            db_session,
            job.id,
            JobStatus.COMPLETED,
            expected_status=JobStatus.STARTED,  # job is QUEUED, not STARTED
        )


async def test_update_status_nonexistent_job_raises_conflict(repo, db_session):
    with pytest.raises(JobStateConflictException):
        await repo.update_status(
            db_session,
            999999,
            JobStatus.STARTED,
            expected_status=JobStatus.QUEUED,
        )
