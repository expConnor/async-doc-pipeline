import re
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from shared.core.exceptions import StorageException
from shared.dtos.document import DocumentDTO

RAW_KEY_PATTERN = re.compile(
    r"^raw/(\d+)/"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.pdf$"
)


def _echo_created(captured):
    """Return a repo.create side_effect that records and echoes the DTO."""

    async def _side_effect(_session, dto):
        captured["dto"] = dto
        return DocumentDTO(
            id=dto.id,
            object_key=dto.object_key,
            file_name=dto.file_name,
            account_id=dto.account_id,
            created_at=datetime(2026, 1, 1),
        )

    return _side_effect


@pytest.fixture
def document_dto():
    return DocumentDTO(
        id=uuid4(),
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

    result = await document_service.create(
        session, account_id=1, file_name="test.pdf"
    )

    assert result.document == document_dto
    assert result.upload_url == "https://s3.example.com/presigned"
    storage.generate_upload_url.assert_called_once_with(document_dto.object_key)


async def test_create_propagates_storage_exception(
    session, document_service, document_repo, storage, document_dto
):
    document_repo.create.return_value = document_dto
    storage.generate_upload_url.side_effect = StorageException()

    with pytest.raises(StorageException):
        await document_service.create(
            session, account_id=1, file_name="test.pdf"
        )


async def test_create_builds_key_from_account_and_document_id(
    session, document_service, document_repo, storage
):
    captured = {}
    document_repo.create.side_effect = _echo_created(captured)
    storage.generate_upload_url.return_value = "https://s3/presigned"

    result = await document_service.create(
        session, account_id=1, file_name="a b#c.pdf"
    )

    dto = captured["dto"]
    match = RAW_KEY_PATTERN.match(dto.object_key)
    assert match is not None, f"unexpected key: {dto.object_key}"
    assert match.group(1) == "1"
    assert UUID(match.group(2)) == dto.id
    assert result.document.id == dto.id


async def test_create_key_contains_no_file_name(
    session, document_service, document_repo, storage
):
    captured = {}
    document_repo.create.side_effect = _echo_created(captured)
    storage.generate_upload_url.return_value = "https://s3/presigned"

    await document_service.create(
        session, account_id=1, file_name="secret-name.pdf"
    )

    assert "secret-name" not in captured["dto"].object_key
