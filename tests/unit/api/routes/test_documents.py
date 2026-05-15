from datetime import UTC, datetime

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
