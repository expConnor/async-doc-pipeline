from abc import ABC, abstractmethod

from ...dtos.document import CreateDocumentDTO, DocumentDTO


class IDocumentRepository(ABC):
    @abstractmethod
    async def create(self, dto: CreateDocumentDTO) -> DocumentDTO: ...

    @abstractmethod
    async def get_by_id(
        self, document_id: int, account_id: int
    ) -> DocumentDTO | None: ...
