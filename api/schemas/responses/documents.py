from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from shared.dtos.artifact import ArtifactType


class CreateDocumentResponse(BaseModel):
    document_id: UUID
    upload_url: str


class DocumentResponse(BaseModel):
    id: UUID
    created_at: datetime


class ArtifactResponse(BaseModel):
    id: UUID
    artifact_type: ArtifactType
    download_url: str


class ListArtifactsResponse(BaseModel):
    artifacts: list[ArtifactResponse]
