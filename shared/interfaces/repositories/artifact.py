from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from ...dtos.artifact import ArtifactDTO, CreateArtifactDTO


class IArtifactRepository(ABC):
    @abstractmethod
    async def create(
        self, session: Any, dto: CreateArtifactDTO
    ) -> ArtifactDTO: ...

    @abstractmethod
    async def list_by_document_id(
        self, session: Any, document_id: UUID, account_id: int
    ) -> list[ArtifactDTO]: ...
