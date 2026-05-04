from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ArtifactDTO:
    job_id: int
    document_id: int
    type: str
    object_key: str
    created_at: datetime


@dataclass(frozen=True)
class CreateArtifactDTO:
    job_id: int
    document_id: int
    type: str
    object_key: str
