from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .artifact import ArtifactType


class JobStatus(str, Enum):
    CREATED = "created"  # Job record exists
    QUEUED = "queued"  # Job record enqueued in message queue
    STARTED = "started"  # worker picked up job
    COMPLETED = "completed"  # worker success
    FAILED = "failed"  # worker failed


@dataclass(frozen=True)
class JobDTO:
    id: int
    account_id: int
    document_id: int
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
    document_id: int
    artifact_types: list[ArtifactType]
