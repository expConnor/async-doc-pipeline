from pydantic import BaseModel

from shared.dtos.artifact import ArtifactType


class ProcessDocumentRequest(BaseModel):
    artifact_types: list[ArtifactType] = [ArtifactType.MARKDOWN]
