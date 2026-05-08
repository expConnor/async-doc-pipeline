from __future__ import annotations

from typing import Any

from app.dtos.job import CreateJobDTO, JobDTO, JobStatus
from app.interfaces.infrastructure.messaging import IMessagingService
from app.interfaces.infrastructure.storage import IStorageService
from app.interfaces.repositories.document import IDocumentRepository
from app.interfaces.repositories.job import IJobRepository
from app.interfaces.services.job import IJobService


class JobService(IJobService):
    def __init__(
        self,
        job_repo: IJobRepository,
        document_repo: IDocumentRepository,
        messaging: IMessagingService,
        storage: IStorageService,
        queue: str,
    ) -> None:
        self._repo = job_repo
        self._document_repo = document_repo
        self._messaging = messaging
        self._storage = storage
        self._queue = queue

    async def get(
        self, session: Any, job_id: int, account_id: int
    ) -> JobDTO | None:
        return await self._repo.get_by_id(session, job_id, account_id)

    async def create(self, session: Any, dto: CreateJobDTO) -> JobDTO:
        document = await self._document_repo.get_by_id(
            session, dto.document_id, dto.account_id
        )
        if document is None:
            raise ValueError("Document not found")
        if not await self._storage.object_exists(document.object_key):
            raise ValueError("Document has not been uploaded")

        job = await self._repo.create(session, dto)
        await self._messaging.enqueue(
            self._queue,
            {
                "job_id": job.id,
                "document_id": job.document_id,
                "artifact_types": [t.value for t in job.artifact_types],
            },
        )
        return await self._repo.update_status(session, job.id, JobStatus.QUEUED)
