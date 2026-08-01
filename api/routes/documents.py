from uuid import UUID

import structlog.contextvars
from fastapi import APIRouter

from api.core.dependencies import (
    ArtifactServiceDep,
    CurrentAccount,
    DBSession,
    DocumentServiceDep,
)
from api.schemas.responses.documents import (
    ArtifactResponse,
    CreateDocumentResponse,
    DocumentResponse,
    ListArtifactsResponse,
)
from shared.core.exceptions import DocumentNotFoundException

router = APIRouter()


@router.post(
    "/documents", response_model=CreateDocumentResponse, status_code=201
)
async def create_document(
    account: CurrentAccount,
    session: DBSession,
    document_service: DocumentServiceDep,
) -> CreateDocumentResponse:
    result = await document_service.create(session, account_id=account.id)
    structlog.contextvars.bind_contextvars(document_id=result.document.id)
    return CreateDocumentResponse(
        document_id=result.document.id,
        upload_url=result.upload_url,
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    account: CurrentAccount,
    session: DBSession,
    document_service: DocumentServiceDep,
) -> DocumentResponse:
    structlog.contextvars.bind_contextvars(document_id=document_id)
    document = await document_service.get(session, document_id, account.id)
    if document is None:
        raise DocumentNotFoundException()
    return DocumentResponse(
        id=document.id,
        created_at=document.created_at,
    )


@router.get(
    "/documents/{document_id}/artifacts", response_model=ListArtifactsResponse
)
async def list_artifacts(
    document_id: UUID,
    account: CurrentAccount,
    session: DBSession,
    artifact_service: ArtifactServiceDep,
) -> ListArtifactsResponse:
    structlog.contextvars.bind_contextvars(document_id=document_id)
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
