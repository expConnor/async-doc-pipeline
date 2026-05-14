import hashlib

from shared.dtos.account import AccountDTO


async def test_authenticate_returns_dto_and_hashes_key(
    session, account_service, account_repo
):
    expected = AccountDTO(id=1, api_key_hash=None)
    account_repo.get_by_api_key_hash.return_value = expected

    result = await account_service.authenticate(session, "my-secret-key")

    expected_hash = hashlib.sha256(b"my-secret-key").hexdigest()
    account_repo.get_by_api_key_hash.assert_called_once_with(
        session, expected_hash
    )
    assert result == expected


async def test_authenticate_returns_none_when_no_match(
    session, account_service, account_repo
):
    account_repo.get_by_api_key_hash.return_value = None

    result = await account_service.authenticate(session, "wrong-key")

    assert result is None
