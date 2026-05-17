import pytest

from shared.core.exceptions import DatabaseException
from shared.dtos.artifact import ArtifactType, CreateArtifactDTO
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


async def test_create_duplicate_object_key_raises_database_exception(
    repo, db_session, account, document, job, artifact
):
    with pytest.raises(DatabaseException):
        await repo.create(
            db_session,
            CreateArtifactDTO(
                job_id=job.id,
                document_id=document.id,
                artifact_type=ArtifactType.MARKDOWN,
                object_key="artifacts/1/test.md",  # same as `artifact` fixture
            ),
        )


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
