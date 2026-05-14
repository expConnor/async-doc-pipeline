from datetime import datetime

import pytest

from shared.core.exceptions import (
    DatabaseException,
    DocumentNotFoundException,
    JobNotFoundException,
    StorageException,
)
from shared.dtos.artifact import ArtifactType
from shared.dtos.document import DocumentDTO
from shared.dtos.job import JobDTO, JobStatus


@pytest.fixture
def job_dto():
    return JobDTO(
        id=10,
        account_id=1,
        document_id=1,
        status=JobStatus.STARTED,
        artifact_types=[ArtifactType.MARKDOWN],
        attempts=1,
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
def document_dto():
    return DocumentDTO(
        id=1,
        object_key="uploads/1/report.pdf",
        file_name="report.pdf",
        account_id=1,
        created_at=datetime(2026, 1, 1),
    )


async def test_job_not_found_raises(session, processing_service, job_repo):
    job_repo.get_for_processing.return_value = None

    with pytest.raises(JobNotFoundException):
        await processing_service.process(session, 10)


async def test_document_not_found_raises(
    session, processing_service, job_repo, document_repo, job_dto
):
    job_repo.get_for_processing.return_value = job_dto
    document_repo.get_by_id.return_value = None

    with pytest.raises(DocumentNotFoundException):
        await processing_service.process(session, 10)


async def test_get_object_storage_exception_propagates(
    session,
    processing_service,
    job_repo,
    document_repo,
    storage,
    job_dto,
    document_dto,
):
    job_repo.get_for_processing.return_value = job_dto
    document_repo.get_by_id.return_value = document_dto
    storage.get_object.side_effect = StorageException()

    with pytest.raises(StorageException):
        await processing_service.process(session, 10)


async def test_parser_exception_propagates(
    session,
    processing_service,
    job_repo,
    document_repo,
    storage,
    parser,
    job_dto,
    document_dto,
):
    job_repo.get_for_processing.return_value = job_dto
    document_repo.get_by_id.return_value = document_dto
    storage.get_object.return_value = b"pdf content"
    parser.parse.side_effect = RuntimeError("parse failed")

    with pytest.raises(RuntimeError, match="parse failed"):
        await processing_service.process(session, 10)


async def test_put_object_storage_exception_propagates(
    session,
    processing_service,
    job_repo,
    document_repo,
    storage,
    parser,
    job_dto,
    document_dto,
):
    job_repo.get_for_processing.return_value = job_dto
    document_repo.get_by_id.return_value = document_dto
    storage.get_object.return_value = b"pdf content"
    parser.parse.return_value = "# Markdown"
    storage.put_object.side_effect = StorageException()

    with pytest.raises(StorageException):
        await processing_service.process(session, 10)


async def test_artifact_create_exception_propagates(
    session,
    processing_service,
    job_repo,
    document_repo,
    storage,
    parser,
    artifact_repo,
    job_dto,
    document_dto,
):
    job_repo.get_for_processing.return_value = job_dto
    document_repo.get_by_id.return_value = document_dto
    storage.get_object.return_value = b"pdf content"
    parser.parse.return_value = "# Markdown"
    artifact_repo.create.side_effect = DatabaseException()

    with pytest.raises(DatabaseException):
        await processing_service.process(session, 10)
