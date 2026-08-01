from datetime import datetime

import pytest
from sqlalchemy import insert

from shared.dtos.artifact import ArtifactType, CreateArtifactDTO
from shared.dtos.job import JobStatus
from shared.infrastructure.models import Job
from shared.infrastructure.repositories.artifact import ArtifactRepository


@pytest.fixture
def repo():
    return ArtifactRepository()


async def test_create_success(repo, db_session, account, document, job):
    dto = await repo.create(
        db_session,
        CreateArtifactDTO(
            job_id=job.id,
            document_id=document.id,
            artifact_type=ArtifactType.MARKDOWN,
            object_key="artifacts/1/test.md",
        ),
    )

    assert dto.id is not None
    assert dto.job_id == job.id
    assert dto.document_id == document.id
    assert dto.artifact_type == ArtifactType.MARKDOWN
    assert dto.object_key == "artifacts/1/test.md"
    assert dto.created_at is not None


async def test_create_same_document_and_type_upserts(
    repo, db_session, account, document, job, artifact
):
    """Reprocessing overwrites the artifact row rather than raising."""
    result = await repo.create(
        db_session,
        CreateArtifactDTO(
            job_id=job.id,
            document_id=document.id,
            artifact_type=ArtifactType.MARKDOWN,
            object_key="artifacts/1/test.md",
        ),
    )

    assert result.id == artifact.id
    assert result.object_key == "artifacts/1/test.md"
    assert result.created_at == artifact.created_at

    rows = await repo.list_by_document_id(db_session, document.id, account.id)
    assert len(rows) == 1


async def test_create_upsert_refreshes_job_id(
    db_session, repo, account, document, job, artifact
):
    """The surviving row points at the run that most recently produced it."""
    second_job = await db_session.execute(
        insert(Job)
        .values(
            account_id=account.id,
            document_id=document.id,
            status=JobStatus.COMPLETED,
            artifact_types=[ArtifactType.MARKDOWN],
            attempts=1,
            max_attempts=3,
            created_at=datetime.now(),
            queued_at=datetime.now(),
        )
        .returning(Job)
    )
    second_job = second_job.scalar_one()

    result = await repo.create(
        db_session,
        CreateArtifactDTO(
            job_id=second_job.id,
            document_id=document.id,
            artifact_type=ArtifactType.MARKDOWN,
            object_key="artifacts/1/test.md",
        ),
    )

    assert result.id == artifact.id
    assert result.job_id == second_job.id
    assert result.created_at == artifact.created_at


async def test_list_by_document_id_returns_artifacts(
    repo, db_session, account, document, artifact
):
    results = await repo.list_by_document_id(
        db_session, document.id, account.id
    )

    assert len(results) == 1
    assert results[0].id == artifact.id
    assert results[0].document_id == document.id


async def test_list_by_document_id_account_isolation(
    repo, db_session, account_b, document, artifact
):
    # account_b does not own the document — the JOIN enforces account isolation
    results = await repo.list_by_document_id(
        db_session, document.id, account_b.id
    )

    assert results == []


async def test_list_by_document_id_empty(repo, db_session, account, document):
    results = await repo.list_by_document_id(
        db_session, document.id, account.id
    )

    assert results == []
