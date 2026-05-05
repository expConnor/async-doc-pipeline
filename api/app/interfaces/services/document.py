from abc import ABC, abstractmethod

from ...dtos.document import CreateDocumentDTO, DocumentWithUploadUrlDTO


class IDocumentService(ABC):
    @abstractmethod
    async def create(
        self, dto: CreateDocumentDTO
    ) -> DocumentWithUploadUrlDTO: ...
