from datetime import UTC, datetime

from shared.core.exceptions import DocumentNotFoundException
from shared.dtos.artifact import ArtifactDTO, ArtifactType, ArtifactWithUrlDTO
from shared.dtos.document import DocumentDTO, DocumentWithUploadUrlDTO
from tests.unit.api.routes.conftest import ACCOUNT, API_KEY

NOW = datetime(2024, 1, 1, tzinfo=UTC)

DOCUMENT_DTO = DocumentDTO(
    id=42,
    object_key="raw/1/some-uuid/report.pdf",
    file_name="report.pdf",
    account_id=ACCOUNT.id,
    created_at=NOW,
)


# POST /documents


async def test_create_document_missing_file_name_returns_422(client):
    response = await client.post(
        "/documents", json={}, headers={"X-API-KEY": API_KEY}
    )
    assert response.status_code == 422
    body = response.json()
    assert "file_name" in body["errors"]


async def test_create_document_success_returns_201(
    client, mock_document_service
):
    mock_document_service.create.return_value = DocumentWithUploadUrlDTO(
        document=DOCUMENT_DTO,
        upload_url="https://s3.example.com/presigned",
    )

    response = await client.post(
        "/documents",
        json={"file_name": "report.pdf"},
        headers={"X-API-KEY": API_KEY},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["document_id"] == 42
    assert body["upload_url"] == "https://s3.example.com/presigned"


# GET /documents/{document_id}


async def test_get_document_success_returns_200(client, mock_document_service):
    mock_document_service.get.return_value = DOCUMENT_DTO

    response = await client.get("/documents/42", headers={"X-API-KEY": API_KEY})

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 42
    assert body["file_name"] == "report.pdf"
    assert "created_at" in body


async def test_get_document_not_found_returns_404(
    client, mock_document_service
):
    mock_document_service.get.return_value = None

    response = await client.get("/documents/99", headers={"X-API-KEY": API_KEY})

    assert response.status_code == 404
    body = response.json()
    assert body["status"] == "error"
    assert body["status_code"] == 404
    assert body["type"] == "DocumentNotFoundException"
    assert body["message"] == "Document not found."
    assert body["errors"] == {}


ARTIFACT_DTO = ArtifactDTO(
    id=7,
    job_id=10,
    document_id=42,
    artifact_type=ArtifactType.MARKDOWN,
    object_key="processed/1/42/output.md",
    created_at=NOW,
)


# GET /documents/{document_id}/artifacts


async def test_list_artifacts_document_not_found_returns_404(
    client, mock_artifact_service
):
    mock_artifact_service.list_for_document.side_effect = (
        DocumentNotFoundException()
    )

    response = await client.get(
        "/documents/99/artifacts", headers={"X-API-KEY": API_KEY}
    )

    assert response.status_code == 404
    assert response.json()["type"] == "DocumentNotFoundException"


async def test_list_artifacts_empty_returns_200_with_empty_list(
    client, mock_artifact_service
):
    mock_artifact_service.list_for_document.return_value = []

    response = await client.get(
        "/documents/42/artifacts", headers={"X-API-KEY": API_KEY}
    )

    assert response.status_code == 200
    assert response.json() == {"artifacts": []}


async def test_list_artifacts_success_returns_200_with_artifacts(
    client, mock_artifact_service
):
    mock_artifact_service.list_for_document.return_value = [
        ArtifactWithUrlDTO(
            artifact=ARTIFACT_DTO,
            download_url="https://s3.example.com/download",
        )
    ]

    response = await client.get(
        "/documents/42/artifacts", headers={"X-API-KEY": API_KEY}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["artifacts"]) == 1
    artifact = body["artifacts"][0]
    assert artifact["id"] == 7
    assert artifact["artifact_type"] == "markdown"
    assert artifact["download_url"] == "https://s3.example.com/download"
