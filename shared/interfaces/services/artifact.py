from abc import ABC, abstractmethod
from typing import Any

from ...dtos.artifact import ArtifactWithUrlDTO


class IArtifactService(ABC):
    @abstractmethod
    async def list_for_document(
        self, session: Any, document_id: int, account_id: int
    ) -> list[ArtifactWithUrlDTO]: ...
