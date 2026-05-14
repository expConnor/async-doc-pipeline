import pytest


@pytest.fixture
def session(mocker):
    return mocker.AsyncMock()
