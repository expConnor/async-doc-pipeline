from tests.unit.api.routes.conftest import API_KEY


async def test_missing_api_key_returns_401(client):
    response = await client.get("/documents/1")
    assert response.status_code == 401
    body = response.json()
    assert body["message"] == "Missing X-API-KEY header"


async def test_invalid_api_key_returns_401(client, mock_account_service):
    mock_account_service.authenticate.return_value = None
    response = await client.get(
        "/documents/1", headers={"X-API-KEY": "bad-key"}
    )
    assert response.status_code == 401
    body = response.json()
    assert body["message"] == "Invalid API key"


async def test_valid_api_key_passes_through(client):
    response = await client.get("/health", headers={"X-API-KEY": API_KEY})
    assert response.status_code == 200
