from pathlib import Path
from typing import Any

from shared.dtos.artifact import ArtifactType, CreateArtifactDTO
from shared.dtos.job import JobStatus
from shared.interfaces.infrastructure.storage import IStorageService
from shared.interfaces.repositories.artifact import IArtifactRepository
from shared.interfaces.repositories.job import IJobRepository

from ..interfaces.parser import IDocumentParser


class ProcessingService:
    def __init__(
        self,
        job_repo: IJobRepository,
        artifact_repo: IArtifactRepository,
        storage: IStorageService,
        parser: IDocumentParser,
    ) -> None:
        self._job_repo = job_repo
        self._artifact_repo = artifact_repo
        self._storage = storage
        self._parser = parser

    async def process(
        self,
        session: Any,
        job_id: int,
        document_id: int,
        object_key: str,
        file_name: str,
    ) -> None:
        await self._job_repo.update_status(session, job_id, JobStatus.STARTED)
        content = await self._storage.get_object(object_key)
        markdown = await self._parser.parse(content)
        key = f"artifacts/{job_id}/{Path(file_name).stem}.md"
        await self._storage.put_object(key, markdown.encode())
        await self._artifact_repo.create(
            session,
            CreateArtifactDTO(job_id, document_id, ArtifactType.MARKDOWN, key),
        )
        await self._job_repo.update_status(session, job_id, JobStatus.COMPLETED)
