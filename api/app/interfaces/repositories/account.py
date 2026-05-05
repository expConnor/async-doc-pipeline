from abc import ABC, abstractmethod
from typing import Any

from ...dtos.account import AccountDTO


class IAccountRepository(ABC):
    @abstractmethod
    async def get_by_api_key_hash(
        self, session: Any, api_key_hash: str
    ) -> AccountDTO | None: ...
