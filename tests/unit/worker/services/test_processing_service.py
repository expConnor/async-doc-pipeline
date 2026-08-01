from datetime import datetime
from uuid import UUID

import pytest

from shared.core.exceptions import (
    DatabaseException,
    DocumentNotFoundException,
    JobNotFoundException,
    StorageException,
)
from shared.dtos.artifact import ArtifactType, CreateArtifactDTO
from shared.dtos.document import DocumentDTO
from shared.dtos.job import JobDTO, JobStatus

JOB_ID = UUID("018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e03")
DOCUMENT_ID = UUID("018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e01")


@pytest.fixture
def job_dto():
    return JobDTO(
        id=JOB_ID,
        account_id=1,
        document_id=DOCUMENT_ID,
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
        id=DOCUMENT_ID,
        object_key="uploads/1/report.pdf",
        account_id=1,
        created_at=datetime(2026, 1, 1),
    )


async def test_job_not_found_raises(session, processing_service, job_repo):
    job_repo.get_for_processing.return_value = None

    with pytest.raises(JobNotFoundException):
        await processing_service.process(session, JOB_ID)


async def test_document_not_found_raises(
    session, processing_service, job_repo, document_repo, job_dto
):
    job_repo.get_for_processing.return_value = job_dto
    document_repo.get_by_id.return_value = None

    with pytest.raises(DocumentNotFoundException):
        await processing_service.process(session, JOB_ID)


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
        await processing_service.process(session, JOB_ID)


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
        await processing_service.process(session, JOB_ID)


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
        await processing_service.process(session, JOB_ID)


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
        await processing_service.process(session, JOB_ID)


async def test_success_creates_artifact_and_completes_job(
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

    await processing_service.process(session, JOB_ID)

    artifact_repo.create.assert_called_once_with(
        session,
        CreateArtifactDTO(
            JOB_ID,
            DOCUMENT_ID,
            ArtifactType.MARKDOWN,
            f"artifacts/{job_dto.account_id}/{DOCUMENT_ID}.md",
        ),
    )
    job_repo.update_status.assert_called_once_with(
        session,
        JOB_ID,
        JobStatus.COMPLETED,
        expected_status=JobStatus.STARTED,
    )


async def test_artifact_key_format(
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

    await processing_service.process(session, JOB_ID)

    _, dto = artifact_repo.create.call_args.args
    assert dto.object_key == f"artifacts/{job_dto.account_id}/{DOCUMENT_ID}.md"


async def test_artifact_key_derives_from_account_and_document(
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
    storage.get_object.return_value = b"%PDF-1.4"
    parser.parse.return_value = "# Heading"

    await processing_service.process(session, job_dto.id)

    key = storage.put_object.call_args.args[0]
    assert key == f"artifacts/{job_dto.account_id}/{document_dto.id}.md"


async def test_artifact_key_omits_job_id(
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
    storage.get_object.return_value = b"%PDF-1.4"
    parser.parse.return_value = "# Heading"

    await processing_service.process(session, job_dto.id)

    assert str(job_dto.id) not in storage.put_object.call_args.args[0]


async def test_reprocessing_targets_the_same_key(
    session,
    processing_service,
    job_repo,
    document_repo,
    storage,
    parser,
    job_dto,
    document_dto,
):
    """Two runs of the same document must address one object, so the
    repository upsert lands on the row it is meant to replace."""
    import dataclasses
    from uuid import uuid4

    document_repo.get_by_id.return_value = document_dto
    storage.get_object.return_value = b"%PDF-1.4"
    parser.parse.return_value = "# Heading"

    job_repo.get_for_processing.return_value = job_dto
    await processing_service.process(session, job_dto.id)
    first_key = storage.put_object.call_args.args[0]

    second_job = dataclasses.replace(job_dto, id=uuid4())
    job_repo.get_for_processing.return_value = second_job
    await processing_service.process(session, second_job.id)
    second_key = storage.put_object.call_args.args[0]

    assert first_key == second_key
