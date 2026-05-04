from abc import ABC, abstractmethod

from ...dtos.job import CreateJobDTO, JobDTO, JobStatus


class IJobRepository(ABC):
    @abstractmethod
    async def create(self, dto: CreateJobDTO) -> JobDTO: ...

    @abstractmethod
    async def get_by_id(
        self, job_id: int, account_id: int
    ) -> JobDTO | None: ...

    @abstractmethod
    async def update_status(self, job_id: int, status: JobStatus) -> JobDTO: ...
