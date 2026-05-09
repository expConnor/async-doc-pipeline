from datetime import datetime

from sqlalchemy import insert, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import DatabaseException
from ...dtos.job import CreateJobDTO, JobDTO, JobStatus
from ...infrastructure.models import Job
from ...interfaces.repositories.job import IJobRepository

_STATUS_TIMESTAMP: dict[JobStatus, str] = {
    JobStatus.QUEUED: "queued_at",
    JobStatus.STARTED: "started_at",
    JobStatus.COMPLETED: "completed_at",
    JobStatus.FAILED: "failed_at",
}

_ACTIVE_STATUSES = {JobStatus.CREATED, JobStatus.QUEUED, JobStatus.STARTED}


class JobRepository(IJobRepository):
    async def create(self, session: AsyncSession, dto: CreateJobDTO) -> JobDTO:
        try:
            query = (
                insert(Job)
                .values(
                    account_id=dto.account_id,
                    document_id=dto.document_id,
                    artifact_types=dto.artifact_types,
                    status=JobStatus.CREATED,
                    created_at=datetime.now(),
                )
                .returning(Job)
            )
            result = await session.execute(query)
            return self._to_dto(result.scalar_one())
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    async def get_by_id(
        self, session: AsyncSession, job_id: int, account_id: int
    ) -> JobDTO | None:
        try:
            query = select(Job).where(
                Job.id == job_id,
                Job.account_id == account_id,
            )
            if job := await session.scalar(query):
                return self._to_dto(job)
            return None
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    async def update_status(
        self, session: AsyncSession, job_id: int, status: JobStatus
    ) -> JobDTO:
        try:
            values: dict = {"status": status}
            if timestamp_col := _STATUS_TIMESTAMP.get(status):
                values[timestamp_col] = datetime.now()
            if status == JobStatus.STARTED:
                values["last_attempt_at"] = datetime.now()
                values["attempts"] = Job.attempts + 1

            query = (
                update(Job)
                .where(Job.id == job_id)
                .values(**values)
                .returning(Job)
            )
            result = await session.execute(query)
            return self._to_dto(result.scalar_one())
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    async def get_active_for_document(
        self, session: AsyncSession, document_id: int, account_id: int
    ) -> JobDTO | None:
        try:
            query = select(Job).where(
                Job.document_id == document_id,
                Job.account_id == account_id,
                Job.status.in_(_ACTIVE_STATUSES),
            )
            if job := await session.scalar(query):
                return self._to_dto(job)
            return None
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    @staticmethod
    def _to_dto(model: Job) -> JobDTO:
        return JobDTO(
            id=model.id,
            account_id=model.account_id,
            document_id=model.document_id,
            status=model.status,
            artifact_types=model.artifact_types,
            attempts=model.attempts,
            max_attempts=model.max_attempts,
            error_message=model.error_message,
            created_at=model.created_at,
            queued_at=model.queued_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            last_attempt_at=model.last_attempt_at,
            failed_at=model.failed_at,
        )
