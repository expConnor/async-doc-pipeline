from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from ...dtos.document import CreateDocumentDTO, DocumentDTO


class IDocumentRepository(ABC):
    @abstractmethod
    async def create(
        self, session: Any, dto: CreateDocumentDTO
    ) -> DocumentDTO: ...

    @abstractmethod
    async def get_by_id(
        self, session: Any, document_id: UUID, account_id: int
    ) -> DocumentDTO | None: ...
