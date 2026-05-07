from app.dtos.artifact import ArtifactType
from pydantic import BaseModel


class CreateDocumentResponse(BaseModel):
    document_id: int
    upload_url: str


class ArtifactResponse(BaseModel):
    id: int
    artifact_type: ArtifactType
    download_url: str


class ListArtifactsResponse(BaseModel):
    artifacts: list[ArtifactResponse]
