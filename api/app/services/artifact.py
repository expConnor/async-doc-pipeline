from __future__ import annotations

from typing import Any

from app.dtos.artifact import ArtifactWithUrlDTO
from app.interfaces.infrastructure.storage import IStorageService
from app.interfaces.repositories.artifact import IArtifactRepository
from app.interfaces.services.artifact import IArtifactService


class ArtifactService(IArtifactService):
    def __init__(
        self,
        artifact_repo: IArtifactRepository,
        storage: IStorageService,
    ) -> None:
        self._repo = artifact_repo
        self._storage = storage

    async def list_for_document(
        self, session: Any, document_id: int, account_id: int
    ) -> list[ArtifactWithUrlDTO]:
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
