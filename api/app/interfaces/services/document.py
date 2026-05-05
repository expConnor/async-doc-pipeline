from abc import ABC, abstractmethod
from typing import Any

from ...dtos.document import CreateDocumentDTO, DocumentWithUploadUrlDTO


class IDocumentService(ABC):
    @abstractmethod
    async def create(
        self, session: Any, dto: CreateDocumentDTO
    ) -> DocumentWithUploadUrlDTO: ...
