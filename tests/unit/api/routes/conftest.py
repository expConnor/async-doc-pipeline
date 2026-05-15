from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from api.app import app
from api.core.providers import (
    get_account_service,
    get_artifact_service,
    get_db_session,
    get_document_service,
    get_job_service,
)
from shared.dtos.account import AccountDTO

ACCOUNT = AccountDTO(id=1, api_key_hash=None)
API_KEY = "test-api-key"


@pytest.fixture
def mock_account_service(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def mock_document_service(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def mock_job_service(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def mock_artifact_service(mocker):
    return mocker.AsyncMock()


@pytest.fixture
async def client(
    mock_account_service,
    mock_document_service,
    mock_job_service,
    mock_artifact_service,
):
    mock_account_service.authenticate.return_value = ACCOUNT

    async def _db_session():
        yield MagicMock()

    original_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db_session] = _db_session
    app.dependency_overrides[get_account_service] = lambda: mock_account_service
    app.dependency_overrides[get_document_service] = lambda: (
        mock_document_service
    )
    app.dependency_overrides[get_job_service] = lambda: mock_job_service
    app.dependency_overrides[get_artifact_service] = lambda: (
        mock_artifact_service
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c
    finally:
        app.dependency_overrides = original_overrides
