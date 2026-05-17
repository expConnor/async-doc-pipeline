from datetime import datetime

import pytest

from shared.core.exceptions import StorageException
from shared.dtos.document import CreateDocumentDTO, DocumentDTO


@pytest.fixture
def document_dto():
    return DocumentDTO(
        id=1,
        object_key="uploads/1.pdf",
        file_name="test.pdf",
        account_id=1,
        created_at=datetime(2026, 1, 1),
    )


async def test_create_returns_document_with_upload_url(
    session, document_service, document_repo, storage, document_dto
):
    document_repo.create.return_value = document_dto
    storage.generate_upload_url.return_value = (
        "https://s3.example.com/presigned"
    )
    dto = CreateDocumentDTO(
        object_key="uploads/1.pdf", file_name="test.pdf", account_id=1
    )

    result = await document_service.create(session, dto)

    assert result.document == document_dto
    assert result.upload_url == "https://s3.example.com/presigned"
    storage.generate_upload_url.assert_called_once_with(document_dto.object_key)


async def test_create_propagates_storage_exception(
    session, document_service, document_repo, storage, document_dto
):
    document_repo.create.return_value = document_dto
    storage.generate_upload_url.side_effect = StorageException()
    dto = CreateDocumentDTO(
        object_key="uploads/1.pdf", file_name="test.pdf", account_id=1
    )

    with pytest.raises(StorageException):
        await document_service.create(session, dto)
