from abc import ABC, abstractmethod

from ...dtos.artifact import ArtifactDTO, CreateArtifactDTO


class IArtifactRepository(ABC):
    @abstractmethod
    async def create(self, dto: CreateArtifactDTO) -> ArtifactDTO: ...

    @abstractmethod
    async def list_by_document_id(
        self, document_id: int, account_id: int
    ) -> list[ArtifactDTO]: ...
