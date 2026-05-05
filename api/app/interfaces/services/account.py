from abc import ABC, abstractmethod

from ...dtos.account import AccountDTO


class IAccountService(ABC):
    @abstractmethod
    async def authenticate(self, api_key: str) -> AccountDTO | None: ...
