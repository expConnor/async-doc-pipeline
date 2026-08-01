from datetime import UTC, datetime
from uuid import UUID

from shared.core.exceptions import (
    ActiveJobExistsException,
    BackpressureException,
    DocumentNotFoundException,
    DocumentNotUploadedException,
)
from shared.dtos.artifact import ArtifactType
from shared.dtos.job import JobDTO, JobStatus
from tests.unit.api.routes.conftest import ACCOUNT, API_KEY

NOW = datetime(2024, 1, 1, tzinfo=UTC)

DOCUMENT_ID = UUID("018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e01")
JOB_ID = UUID("018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e03")
MISSING_ID = UUID("018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e99")

JOB_DTO = JobDTO(
    id=JOB_ID,
    account_id=ACCOUNT.id,
    document_id=DOCUMENT_ID,
    status=JobStatus.QUEUED,
    artifact_types=[ArtifactType.MARKDOWN],
    attempts=0,
    max_attempts=3,
    error_message=None,
    created_at=NOW,
    queued_at=NOW,
    started_at=None,
    completed_at=None,
    last_attempt_at=None,
    failed_at=None,
)


# POST /documents/{document_id}/process


async def test_process_document_invalid_artifact_type_returns_422(client):
    response = await client.post(
        f"/documents/{DOCUMENT_ID}/process",
        json={"artifact_types": ["invalid_type"]},
        headers={"X-API-KEY": API_KEY},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["errors"]


async def test_process_document_not_found_returns_404(client, mock_job_service):
    mock_job_service.create.side_effect = DocumentNotFoundException()

    response = await client.post(
        f"/documents/{MISSING_ID}/process",
        json={},
        headers={"X-API-KEY": API_KEY},
    )

    assert response.status_code == 404
    assert response.json()["type"] == "DocumentNotFoundException"


async def test_process_document_not_uploaded_returns_409(
    client, mock_job_service
):
    mock_job_service.create.side_effect = DocumentNotUploadedException()

    response = await client.post(
        f"/documents/{DOCUMENT_ID}/process",
        json={},
        headers={"X-API-KEY": API_KEY},
    )

    assert response.status_code == 409
    assert response.json()["type"] == "DocumentNotUploadedException"


async def test_process_document_backpressure_returns_429(
    client, mock_job_service
):
    mock_job_service.create.side_effect = BackpressureException()

    response = await client.post(
        f"/documents/{DOCUMENT_ID}/process",
        json={},
        headers={"X-API-KEY": API_KEY},
    )

    assert response.status_code == 429
    assert response.json()["type"] == "BackpressureException"


async def test_process_document_active_job_returns_409(
    client, mock_job_service
):
    mock_job_service.create.side_effect = ActiveJobExistsException()

    response = await client.post(
        f"/documents/{DOCUMENT_ID}/process",
        json={},
        headers={"X-API-KEY": API_KEY},
    )

    assert response.status_code == 409
    assert response.json()["type"] == "ActiveJobExistsException"


async def test_process_document_success_returns_201(client, mock_job_service):
    mock_job_service.create.return_value = JOB_DTO

    response = await client.post(
        f"/documents/{DOCUMENT_ID}/process",
        json={"artifact_types": ["markdown"]},
        headers={"X-API-KEY": API_KEY},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == str(JOB_ID)
    assert body["document_id"] == str(DOCUMENT_ID)
    assert body["status"] == "queued"
    assert body["artifact_types"] == ["markdown"]


# GET /jobs/{job_id}


async def test_get_job_not_found_returns_404(client, mock_job_service):
    mock_job_service.get.return_value = None

    response = await client.get(
        f"/jobs/{MISSING_ID}", headers={"X-API-KEY": API_KEY}
    )

    assert response.status_code == 404
    assert response.json()["type"] == "JobNotFoundException"


async def test_get_job_success_returns_200_with_all_fields(
    client, mock_job_service
):
    mock_job_service.get.return_value = JOB_DTO

    response = await client.get(
        f"/jobs/{JOB_ID}", headers={"X-API-KEY": API_KEY}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(JOB_ID)
    assert body["document_id"] == str(DOCUMENT_ID)
    assert body["status"] == "queued"
    assert body["artifact_types"] == ["markdown"]
    assert body["attempts"] == 0
    assert body["max_attempts"] == 3
    assert body["error_message"] is None
    assert "created_at" in body
    assert "queued_at" in body
    assert body["started_at"] is None
    assert body["completed_at"] is None
    assert body["last_attempt_at"] is None
    assert body["failed_at"] is None
