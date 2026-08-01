from uuid import uuid4

import pytest

from shared.core.exceptions import DatabaseException
from shared.dtos.document import CreateDocumentDTO
from shared.infrastructure.repositories.document import DocumentRepository


@pytest.fixture
def repo():
    return DocumentRepository()


async def test_create_success(repo, db_session, account):
    dto = await repo.create(
        db_session,
        CreateDocumentDTO(
            object_key="uploads/new.pdf",
            file_name="new.pdf",
            account_id=account.id,
        ),
    )

    assert dto.id is not None
    assert dto.object_key == "uploads/new.pdf"
    assert dto.file_name == "new.pdf"
    assert dto.account_id == account.id
    assert dto.created_at is not None


async def test_create_duplicate_object_key_raises_database_exception(
    repo, db_session, account, document
):
    with pytest.raises(DatabaseException):
        await repo.create(
            db_session,
            CreateDocumentDTO(
                object_key="uploads/test.pdf",  # same as `document` fixture
                file_name="other.pdf",
                account_id=account.id,
            ),
        )


async def test_create_nonexistent_account_raises_database_exception(
    repo, db_session
):
    with pytest.raises(DatabaseException):
        await repo.create(
            db_session,
            CreateDocumentDTO(
                object_key="uploads/orphan.pdf",
                file_name="orphan.pdf",
                account_id=999999,
            ),
        )


async def test_get_by_id_matching_account(repo, db_session, account, document):
    dto = await repo.get_by_id(db_session, document.id, account.id)

    assert dto is not None
    assert dto.id == document.id
    assert dto.account_id == account.id


async def test_get_by_id_mismatched_account(
    repo, db_session, account_b, document
):
    dto = await repo.get_by_id(db_session, document.id, account_b.id)

    assert dto is None


async def test_get_by_id_nonexistent(repo, db_session, account):
    dto = await repo.get_by_id(db_session, uuid4(), account.id)

    assert dto is None
