from unittest.mock import AsyncMock

import pytest

from api.middleware import LoggingMiddleware


@pytest.fixture
def mock_logger(mocker):
    return mocker.patch("api.middleware.logger")


async def test_non_http_scope_passes_through_unchanged(mock_logger):
    inner = AsyncMock()
    middleware = LoggingMiddleware(inner)
    scope = {"type": "lifespan"}
    receive = AsyncMock()
    send = AsyncMock()

    await middleware(scope, receive, send)

    inner.assert_called_once_with(scope, receive, send)
    mock_logger.info.assert_not_called()


async def test_http_scope_captures_response_status_code(mock_logger):
    async def inner(scope, receive, send):
        msg = {"type": "http.response.start", "status": 201, "headers": []}
        await send(msg)
        await send({"type": "http.response.body", "body": b""})

    middleware = LoggingMiddleware(inner)
    scope = {"type": "http", "method": "POST", "path": "/documents"}

    await middleware(scope, AsyncMock(), AsyncMock())

    mock_logger.info.assert_called_once()
    kwargs = mock_logger.info.call_args.kwargs
    assert kwargs["status"] == 201


async def test_http_scope_defaults_500_when_response_never_starts(mock_logger):
    async def inner(scope, receive, send):
        raise RuntimeError("inner app crashed before responding")

    middleware = LoggingMiddleware(inner)
    scope = {"type": "http", "method": "GET", "path": "/documents/1"}

    with pytest.raises(RuntimeError):
        await middleware(scope, AsyncMock(), AsyncMock())

    mock_logger.info.assert_called_once()
    kwargs = mock_logger.info.call_args.kwargs
    assert kwargs["status"] == 500
