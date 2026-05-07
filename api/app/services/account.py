from __future__ import annotations

import hashlib
from typing import Any

from app.dtos.account import AccountDTO
from app.interfaces.repositories.account import IAccountRepository
from app.interfaces.services.account import IAccountService


class AccountService(IAccountService):
    def __init__(self, account_repo: IAccountRepository) -> None:
        self._repo = account_repo

    async def authenticate(
        self, session: Any, api_key: str
    ) -> AccountDTO | None:
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        return await self._repo.get_by_api_key_hash(session, key_hash)
