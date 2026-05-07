from app.dtos.artifact import ArtifactType
from pydantic import BaseModel


class ProcessDocumentRequest(BaseModel):
    artifact_types: list[ArtifactType] = [ArtifactType.MARKDOWN]
