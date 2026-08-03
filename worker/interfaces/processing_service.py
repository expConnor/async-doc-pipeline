from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID


class IProcessingService(ABC):
    @abstractmethod
    async def process(self, session: Any, job_id: UUID) -> None: ...
