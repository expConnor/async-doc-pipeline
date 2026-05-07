from uuid import uuid4

from app.api.schemas.requests.documents import CreateDocumentRequest
from app.api.schemas.responses.documents import (
    ArtifactResponse,
    CreateDocumentResponse,
    ListArtifactsResponse,
)
from app.core.dependencies import (
    ArtifactServiceDep,
    CurrentAccount,
    DBSession,
    DocumentServiceDep,
)
from app.dtos.document import CreateDocumentDTO
from fastapi import APIRouter

router = APIRouter()


@router.post(
    "/documents", response_model=CreateDocumentResponse, status_code=201
)
async def create_document(
    body: CreateDocumentRequest,
    account: CurrentAccount,
    session: DBSession,
    document_service: DocumentServiceDep,
) -> CreateDocumentResponse:
    object_key = f"raw/{account.id}/{uuid4()}/{body.file_name}"
    dto = CreateDocumentDTO(
        object_key=object_key,
        file_name=body.file_name,
        account_id=account.id,
    )
    result = await document_service.create(session, dto)
    return CreateDocumentResponse(
        document_id=result.document.id,
        upload_url=result.upload_url,
    )


@router.get(
    "/documents/{document_id}/artifacts", response_model=ListArtifactsResponse
)
async def list_artifacts(
    document_id: int,
    account: CurrentAccount,
    session: DBSession,
    artifact_service: ArtifactServiceDep,
) -> ListArtifactsResponse:
    artifacts = await artifact_service.list_for_document(
        session, document_id, account.id
    )
    return ListArtifactsResponse(
        artifacts=[
            ArtifactResponse(
                id=a.artifact.id,
                artifact_type=a.artifact.artifact_type,
                download_url=a.download_url,
            )
            for a in artifacts
        ]
    )
