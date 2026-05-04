from abc import ABC, abstractmethod

from ...dtos.account import AccountDTO


class IAccountRepository(ABC):
    @abstractmethod
    async def get_by_api_key_hash(
        self, api_key_hash: str
    ) -> AccountDTO | None: ...
