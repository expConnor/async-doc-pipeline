from tests.unit.api.routes.conftest import API_KEY


async def test_health_returns_200_with_status(client):
    response = await client.get("/health", headers={"X-API-KEY": API_KEY})
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
