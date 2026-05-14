from datetime import datetime

import pytest

from shared.core.exceptions import DocumentNotFoundException, StorageException
from shared.dtos.artifact import ArtifactDTO, ArtifactType, ArtifactWithUrlDTO
from shared.dtos.document import DocumentDTO


@pytest.fixture
def document_dto():
    return DocumentDTO(
        id=1,
        object_key="uploads/1.pdf",
        file_name="test.pdf",
        account_id=1,
        created_at=datetime(2026, 1, 1),
    )


def _make_artifact(id_: int, key: str) -> ArtifactDTO:
    return ArtifactDTO(
        id=id_,
        job_id=10,
        document_id=1,
        artifact_type=ArtifactType.MARKDOWN,
        object_key=key,
        created_at=datetime(2026, 1, 1),
    )


async def test_list_raises_when_document_not_found(
    session, artifact_service, document_repo
):
    document_repo.get_by_id.return_value = None

    with pytest.raises(DocumentNotFoundException):
        await artifact_service.list_for_document(
            session, document_id=1, account_id=1
        )


async def test_list_returns_empty_for_no_artifacts(
    session, artifact_service, document_repo, artifact_repo, document_dto
):
    document_repo.get_by_id.return_value = document_dto
    artifact_repo.list_by_document_id.return_value = []

    result = await artifact_service.list_for_document(
        session, document_id=1, account_id=1
    )

    assert result == []


async def test_list_returns_artifact_with_url_per_artifact(
    session,
    artifact_service,
    document_repo,
    artifact_repo,
    storage,
    document_dto,
):
    a1 = _make_artifact(1, "artifacts/1.md")
    a2 = _make_artifact(2, "artifacts/2.md")
    document_repo.get_by_id.return_value = document_dto
    artifact_repo.list_by_document_id.return_value = [a1, a2]
    storage.generate_download_url.side_effect = ["https://url1", "https://url2"]

    result = await artifact_service.list_for_document(
        session, document_id=1, account_id=1
    )

    assert len(result) == 2
    assert result[0] == ArtifactWithUrlDTO(
        artifact=a1, download_url="https://url1"
    )
    assert result[1] == ArtifactWithUrlDTO(
        artifact=a2, download_url="https://url2"
    )
    assert storage.generate_download_url.call_count == 2


async def test_list_propagates_storage_exception_mid_loop(
    session,
    artifact_service,
    document_repo,
    artifact_repo,
    storage,
    document_dto,
):
    a1 = _make_artifact(1, "artifacts/1.md")
    document_repo.get_by_id.return_value = document_dto
    artifact_repo.list_by_document_id.return_value = [a1]
    storage.generate_download_url.side_effect = StorageException()

    with pytest.raises(StorageException):
        await artifact_service.list_for_document(
            session, document_id=1, account_id=1
        )
