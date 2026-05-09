from abc import ABC, abstractmethod
from typing import Any

from ...dtos.account import AccountDTO


class IAccountService(ABC):
    @abstractmethod
    async def authenticate(
        self, session: Any, api_key: str
    ) -> AccountDTO | None: ...
