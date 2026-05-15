import json
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError

from api.app import (
    http_exception_handler,
    internal_exception_handler,
    validation_exception_handler,
)
from shared.core.exceptions import DocumentNotFoundException, StorageException


@pytest.fixture
def request_():
    return MagicMock(spec=Request)


# AppException handler


async def test_app_exception_lt_500_returns_envelope_shape(request_):
    exc = DocumentNotFoundException()
    response = await internal_exception_handler(request_, exc)

    assert response.status_code == 404
    body = json.loads(response.body)
    assert body["status"] == "error"
    assert body["status_code"] == 404
    assert body["type"] == "DocumentNotFoundException"
    assert body["message"] == "Document not found."
    assert body["errors"] == {}


async def test_app_exception_lt_500_logs_at_warning(request_, mocker):
    mock_logger = mocker.patch("api.app.logger")
    exc = DocumentNotFoundException()
    await internal_exception_handler(request_, exc)
    mock_logger.warning.assert_called_once()
    mock_logger.error.assert_not_called()


async def test_app_exception_gte_500_logs_at_error(request_, mocker):
    mock_logger = mocker.patch("api.app.logger")
    exc = StorageException()
    await internal_exception_handler(request_, exc)
    mock_logger.error.assert_called_once()
    mock_logger.warning.assert_not_called()


# HTTPException handler


async def test_http_exception_string_detail_is_message(request_):
    exc = HTTPException(status_code=400, detail="Bad input")
    response = await http_exception_handler(request_, exc)

    body = json.loads(response.body)
    assert response.status_code == 400
    assert body["message"] == "Bad input"
    assert body["type"] == "HTTPException"
    assert body["errors"] == {}


async def test_http_exception_non_string_detail_is_json_dumped(request_):
    detail = {"code": "QUOTA_EXCEEDED", "limit": 100}
    exc = HTTPException(status_code=429, detail=detail)
    response = await http_exception_handler(request_, exc)

    body = json.loads(response.body)
    assert response.status_code == 429
    assert body["message"] == json.dumps(detail)


# RequestValidationError handler


async def test_validation_error_extracts_field_from_loc(request_, mocker):
    exc = mocker.MagicMock(spec=RequestValidationError)
    exc.errors.return_value = [
        {
            "loc": ("body", "file_name"),
            "msg": "Field required",
            "type": "missing",
        }
    ]
    response = await validation_exception_handler(request_, exc)

    body = json.loads(response.body)
    assert response.status_code == 422
    assert body["type"] == "RequestValidationError"
    assert body["message"] == "Request validation failed."
    assert "file_name" in body["errors"]


async def test_validation_error_empty_loc_uses_body_key(request_, mocker):
    exc = mocker.MagicMock(spec=RequestValidationError)
    exc.errors.return_value = [
        {"loc": (), "msg": "invalid", "type": "value_error"}
    ]
    response = await validation_exception_handler(request_, exc)

    body = json.loads(response.body)
    assert "body" in body["errors"]
