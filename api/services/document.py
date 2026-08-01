from __future__ import annotations

from typing import Any
from uuid import UUID

from shared.dtos.document import (
    CreateDocumentDTO,
    DocumentDTO,
    DocumentWithUploadUrlDTO,
)
from shared.interfaces.infrastructure.storage import IStorageService
from shared.interfaces.repositories.document import IDocumentRepository
from shared.interfaces.services.document import IDocumentService


class DocumentService(IDocumentService):
    def __init__(
        self,
        document_repo: IDocumentRepository,
        storage: IStorageService,
    ) -> None:
        self._repo = document_repo
        self._storage = storage

    async def create(
        self, session: Any, dto: CreateDocumentDTO
    ) -> DocumentWithUploadUrlDTO:
        document = await self._repo.create(session, dto)
        upload_url = await self._storage.generate_upload_url(
            document.object_key
        )
        return DocumentWithUploadUrlDTO(
            document=document, upload_url=upload_url
        )

    async def get(
        self, session: Any, document_id: UUID, account_id: int
    ) -> DocumentDTO | None:
        return await self._repo.get_by_id(session, document_id, account_id)
