from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from .artifact import ArtifactType


class JobStatus(StrEnum):
    QUEUED = "queued"  # Job record exists and is enqueued
    STARTED = "started"  # Worker picked up job
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class JobDTO:
    id: UUID
    account_id: int
    document_id: UUID
    status: JobStatus
    artifact_types: list[ArtifactType]
    attempts: int
    max_attempts: int
    error_message: str | None
    created_at: datetime
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    last_attempt_at: datetime | None
    failed_at: datetime | None


@dataclass(frozen=True)
class CreateJobDTO:
    account_id: int
    document_id: UUID
    artifact_types: list[ArtifactType]
