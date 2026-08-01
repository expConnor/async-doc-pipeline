from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from ...dtos.job import CreateJobDTO, JobDTO, JobStatus


class IJobRepository(ABC):
    @abstractmethod
    async def create(self, session: Any, dto: CreateJobDTO) -> JobDTO: ...

    @abstractmethod
    async def get_by_id(
        self, session: Any, job_id: UUID, account_id: int
    ) -> JobDTO | None: ...

    @abstractmethod
    async def update_status(
        self,
        session: Any,
        job_id: UUID,
        status: JobStatus,
        *,
        expected_status: JobStatus,
        error_message: str | None = None,
    ) -> JobDTO: ...

    @abstractmethod
    async def get_for_processing(
        self, session: Any, job_id: UUID
    ) -> JobDTO | None: ...
