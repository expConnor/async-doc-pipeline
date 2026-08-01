from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from ...dtos.document import (
    DocumentDTO,
    DocumentWithUploadUrlDTO,
)


class IDocumentService(ABC):
    @abstractmethod
    async def create(
        self, session: Any, account_id: int, file_name: str
    ) -> DocumentWithUploadUrlDTO: ...

    @abstractmethod
    async def get(
        self, session: Any, document_id: UUID, account_id: int
    ) -> DocumentDTO | None: ...
