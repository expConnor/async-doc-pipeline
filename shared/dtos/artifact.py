from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ArtifactType(StrEnum):
    MARKDOWN = "markdown"


@dataclass(frozen=True)
class ArtifactDTO:
    id: UUID
    job_id: UUID
    document_id: UUID
    artifact_type: ArtifactType
    object_key: str
    created_at: datetime


@dataclass(frozen=True)
class ArtifactWithUrlDTO:
    artifact: ArtifactDTO
    download_url: str


@dataclass(frozen=True)
class CreateArtifactDTO:
    job_id: UUID
    document_id: UUID
    artifact_type: ArtifactType
    object_key: str
