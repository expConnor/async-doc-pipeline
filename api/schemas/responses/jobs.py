from datetime import datetime

from pydantic import BaseModel

from shared.dtos.artifact import ArtifactType
from shared.dtos.job import JobStatus


class JobResponse(BaseModel):
    id: int
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
