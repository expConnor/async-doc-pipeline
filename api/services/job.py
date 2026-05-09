from __future__ import annotations

from typing import Any

from shared.core.exceptions import (
    ActiveJobExistsException,
    BackpressureException,
    DocumentNotFoundException,
    DocumentNotUploadedException,
)
from shared.dtos.job import CreateJobDTO, JobDTO, JobStatus
from shared.interfaces.infrastructure.messaging import IMessagingService
from shared.interfaces.infrastructure.storage import IStorageService
from shared.interfaces.repositories.document import IDocumentRepository
from shared.interfaces.repositories.job import IJobRepository
from shared.interfaces.services.job import IJobService


class JobService(IJobService):
    def __init__(
        self,
        job_repo: IJobRepository,
        document_repo: IDocumentRepository,
        messaging: IMessagingService,
        storage: IStorageService,
        queue: str,
        backpressure_threshold: int,
    ) -> None:
        self._repo = job_repo
        self._document_repo = document_repo
        self._messaging = messaging
        self._storage = storage
        self._queue = queue
        self._backpressure_threshold = backpressure_threshold

    async def get(
        self, session: Any, job_id: int, account_id: int
    ) -> JobDTO | None:
        return await self._repo.get_by_id(session, job_id, account_id)

    async def create(self, session: Any, dto: CreateJobDTO) -> JobDTO:
        document = await self._document_repo.get_by_id(
            session, dto.document_id, dto.account_id
        )
        if document is None:
            raise DocumentNotFoundException()
        if not await self._storage.object_exists(document.object_key):
            raise DocumentNotUploadedException()

        if (
            await self._repo.get_active_for_document(
                session, dto.document_id, dto.account_id
            )
            is not None
        ):
            raise ActiveJobExistsException()

        depth = await self._messaging.queue_depth(self._queue)
        if depth >= self._backpressure_threshold:
            raise BackpressureException()

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
