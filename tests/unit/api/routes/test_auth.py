from tests.unit.api.routes.conftest import API_KEY

DOCUMENT_URL = "/documents/018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e01"


async def test_missing_api_key_returns_401(client):
    response = await client.get(DOCUMENT_URL)
    assert response.status_code == 401
    body = response.json()
    assert body["message"] == "Missing X-API-KEY header"


async def test_invalid_api_key_returns_401(client, mock_account_service):
    mock_account_service.authenticate.return_value = None
    response = await client.get(DOCUMENT_URL, headers={"X-API-KEY": "bad-key"})
    assert response.status_code == 401
    body = response.json()
    assert body["message"] == "Invalid API key"


async def test_valid_api_key_passes_through(
    client, mock_document_service, mock_account_service
):
    mock_document_service.get.return_value = None
    response = await client.get(DOCUMENT_URL, headers={"X-API-KEY": API_KEY})
    assert response.status_code == 404
    mock_account_service.authenticate.assert_awaited_once()
