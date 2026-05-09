from __future__ import annotations

from typing import Any

from shared.core.exceptions import DocumentNotFoundException
from shared.dtos.artifact import ArtifactWithUrlDTO
from shared.interfaces.infrastructure.storage import IStorageService
from shared.interfaces.repositories.artifact import IArtifactRepository
from shared.interfaces.repositories.document import IDocumentRepository
from shared.interfaces.services.artifact import IArtifactService


class ArtifactService(IArtifactService):
    def __init__(
        self,
        artifact_repo: IArtifactRepository,
        storage: IStorageService,
        document_repo: IDocumentRepository,
    ) -> None:
        self._repo = artifact_repo
        self._storage = storage
        self._document_repo = document_repo

    async def list_for_document(
        self, session: Any, document_id: int, account_id: int
    ) -> list[ArtifactWithUrlDTO]:
        document = await self._document_repo.get_by_id(
            session, document_id, account_id
        )
        if document is None:
            raise DocumentNotFoundException()
        artifacts = await self._repo.list_by_document_id(
            session, document_id, account_id
        )
        result = []
        for artifact in artifacts:
            url = await self._storage.generate_download_url(artifact.object_key)
            result.append(
                ArtifactWithUrlDTO(artifact=artifact, download_url=url)
            )
        return result
