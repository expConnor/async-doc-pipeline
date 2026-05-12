from abc import ABC, abstractmethod
from typing import Any


class IProcessingService(ABC):
    @abstractmethod
    async def process(self, session: Any, job_id: int) -> None: ...
