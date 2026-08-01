from datetime import datetime
from uuid import uuid4

import pytest

from shared.core.exceptions import (
    BackpressureException,
    DocumentNotFoundException,
    DocumentNotUploadedException,
    QueueException,
    StorageException,
)
from shared.dtos.artifact import ArtifactType
from shared.dtos.document import DocumentDTO
from shared.dtos.job import CreateJobDTO, JobDTO, JobStatus


@pytest.fixture
def document_dto():
    return DocumentDTO(
        id=uuid4(),
        object_key="uploads/1.pdf",
        account_id=1,
        created_at=datetime(2026, 1, 1),
    )


@pytest.fixture
def job_dto():
    return JobDTO(
        id=uuid4(),
        account_id=1,
        document_id=uuid4(),
        status=JobStatus.QUEUED,
        artifact_types=[ArtifactType.MARKDOWN],
        attempts=0,
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
def create_dto():
    return CreateJobDTO(
        account_id=1,
        document_id=uuid4(),
        artifact_types=[ArtifactType.MARKDOWN],
    )


async def test_create_raises_when_document_not_found(
    session, job_service, document_repo, create_dto
):
    document_repo.get_by_id.return_value = None

    with pytest.raises(DocumentNotFoundException):
        await job_service.create(session, create_dto)


async def test_create_raises_when_document_not_uploaded(
    session, job_service, document_repo, storage, document_dto, create_dto
):
    document_repo.get_by_id.return_value = document_dto
    storage.object_exists.return_value = False

    with pytest.raises(DocumentNotUploadedException):
        await job_service.create(session, create_dto)


async def test_create_propagates_storage_exception_on_exists_check(
    session, job_service, document_repo, storage, document_dto, create_dto
):
    document_repo.get_by_id.return_value = document_dto
    storage.object_exists.side_effect = StorageException()

    with pytest.raises(StorageException):
        await job_service.create(session, create_dto)


async def test_create_raises_backpressure_when_depth_at_threshold(
    session,
    job_service,
    document_repo,
    storage,
    messaging,
    document_dto,
    create_dto,
):
    document_repo.get_by_id.return_value = document_dto
    storage.object_exists.return_value = True
    messaging.queue_depth.return_value = 10  # == backpressure_threshold

    with pytest.raises(BackpressureException):
        await job_service.create(session, create_dto)


async def test_create_raises_backpressure_when_depth_above_threshold(
    session,
    job_service,
    document_repo,
    storage,
    messaging,
    document_dto,
    create_dto,
):
    document_repo.get_by_id.return_value = document_dto
    storage.object_exists.return_value = True
    messaging.queue_depth.return_value = 11

    with pytest.raises(BackpressureException):
        await job_service.create(session, create_dto)


async def test_create_success_when_depth_below_threshold(
    session,
    job_service,
    document_repo,
    storage,
    messaging,
    job_repo,
    document_dto,
    job_dto,
    create_dto,
):
    document_repo.get_by_id.return_value = document_dto
    storage.object_exists.return_value = True
    messaging.queue_depth.return_value = 9  # < backpressure_threshold=10
    job_repo.create.return_value = job_dto

    result = await job_service.create(session, create_dto)

    assert result == job_dto
    job_repo.create.assert_called_once()
    messaging.enqueue.assert_called_once_with(
        "jobs",
        {
            "job_id": str(job_dto.id),
            "document_id": str(job_dto.document_id),
            "artifact_types": [ArtifactType.MARKDOWN.value],
        },
    )
    session.commit.assert_called_once()


async def test_create_propagates_queue_exception_after_commit(
    session,
    job_service,
    document_repo,
    storage,
    messaging,
    job_repo,
    document_dto,
    job_dto,
    create_dto,
):
    document_repo.get_by_id.return_value = document_dto
    storage.object_exists.return_value = True
    messaging.queue_depth.return_value = 9
    job_repo.create.return_value = job_dto
    messaging.enqueue.side_effect = QueueException()

    # Job was committed to DB; only the exception surfaces.
    with pytest.raises(QueueException):
        await job_service.create(session, create_dto)
