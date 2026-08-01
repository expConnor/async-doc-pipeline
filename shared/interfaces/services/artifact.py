from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from ...dtos.artifact import ArtifactWithUrlDTO


class IArtifactService(ABC):
    @abstractmethod
    async def list_for_document(
        self, session: Any, document_id: UUID, account_id: int
    ) -> list[ArtifactWithUrlDTO]: ...
