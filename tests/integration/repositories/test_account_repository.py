import pytest

from shared.infrastructure.repositories.account import AccountRepository


@pytest.fixture
def repo():
    return AccountRepository()


async def test_get_by_api_key_hash_match(repo, db_session, account):
    dto = await repo.get_by_api_key_hash(db_session, "hash_account_a")

    assert dto is not None
    assert dto.id == account.id
    assert dto.api_key_hash == "hash_account_a"


async def test_get_by_api_key_hash_no_match(repo, db_session, account):
    dto = await repo.get_by_api_key_hash(db_session, "nonexistent_hash")

    assert dto is None


async def test_get_by_api_key_hash_to_dto_field_completeness(
    repo, db_session, account
):
    dto = await repo.get_by_api_key_hash(db_session, "hash_account_a")

    assert dto is not None
    assert dto.id == account.id
    assert dto.api_key_hash == account.api_key_hash
