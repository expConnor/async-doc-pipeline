from datetime import datetime

from pydantic import BaseModel

from shared.dtos.artifact import ArtifactType


class CreateDocumentResponse(BaseModel):
    document_id: int
    upload_url: str


class DocumentResponse(BaseModel):
    id: int
    file_name: str
    created_at: datetime


class ArtifactResponse(BaseModel):
    id: int
    artifact_type: ArtifactType
    download_url: str


class ListArtifactsResponse(BaseModel):
    artifacts: list[ArtifactResponse]
