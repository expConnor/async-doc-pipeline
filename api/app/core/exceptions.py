from __future__ import annotations

from typing import Any


class AppException(Exception):
    _status_code: int = 500
    _message: str = "An unexpected error occurred."
    _errors: dict[str, Any] = {}

    def __init__(
        self,
        status_code: int | None = None,
        message: str | None = None,
        errors: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.errors = errors

    def get_status_code(self) -> int:
        return self.status_code or self._status_code

    def get_message(self) -> str:
        return self.message or self._message

    def get_errors(self) -> dict[str, Any]:
        return self.errors or self._errors


class DocumentNotFoundException(AppException):
    _status_code = 404
    _message = "Document not found."


class DocumentNotUploadedException(AppException):
    _status_code = 409
    _message = "Document has not been uploaded."


class JobNotFoundException(AppException):
    _status_code = 404
    _message = "Job not found."


class StorageException(AppException):
    _status_code = 503
    _message = "Storage service unavailable."


class QueueException(AppException):
    _status_code = 503
    _message = "Queue service unavailable."


class DatabaseException(AppException):
    _status_code = 503
    _message = "Database service unavailable."
