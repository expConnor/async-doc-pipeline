from abc import ABC, abstractmethod
from typing import Any

from ...dtos.job import CreateJobDTO, JobDTO


class IJobService(ABC):
    @abstractmethod
    async def get(
        self, session: Any, job_id: int, account_id: int
    ) -> JobDTO | None: ...

    @abstractmethod
    async def create(self, session: Any, dto: CreateJobDTO) -> JobDTO: ...
