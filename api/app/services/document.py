from __future__ import annotations

from typing import Any

from app.dtos.document import CreateDocumentDTO, DocumentWithUploadUrlDTO
from app.interfaces.infrastructure.storage import IStorageService
from app.interfaces.repositories.document import IDocumentRepository
from app.interfaces.services.document import IDocumentService


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
