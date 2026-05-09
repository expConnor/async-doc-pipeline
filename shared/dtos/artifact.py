from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ArtifactType(str, Enum):
    MARKDOWN = "markdown"


@dataclass(frozen=True)
class ArtifactDTO:
    id: int
    job_id: int
    document_id: int
    artifact_type: ArtifactType
    object_key: str
    created_at: datetime


@dataclass(frozen=True)
class ArtifactWithUrlDTO:
    artifact: ArtifactDTO
    download_url: str


@dataclass(frozen=True)
class CreateArtifactDTO:
    job_id: int
    document_id: int
    artifact_type: ArtifactType
    object_key: str
