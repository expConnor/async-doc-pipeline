from abc import ABC, abstractmethod

from ...dtos.job import CreateJobDTO, JobDTO


class IJobService(ABC):
    @abstractmethod
    async def get(self, job_id: int, account_id: int) -> JobDTO | None: ...

    @abstractmethod
    async def create(self, dto: CreateJobDTO) -> JobDTO: ...
