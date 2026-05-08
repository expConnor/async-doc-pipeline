# Error Handling Design

**Date:** 2026-05-08
**Branch:** `api/implement-proper-errorhandling-20`

## Problem

The current codebase has inconsistent, leaky error handling:

- Services raise bare `ValueError` for domain errors, forcing routes to catch a generic exception and blindly map it to a single HTTP status code. "Document not found" and "Document not uploaded" both map to 409, which is wrong for the first case.
- `GET /documents/{id}/artifacts` silently returns an empty list when the document doesn't exist; it should return 404.
- Auth errors are inline `HTTPException` raises scattered across `security.py` and `dependencies.py`.
- Infrastructure failures (S3, RabbitMQ, DB) are completely unhandled and surface as 500s with no semantic context.
- No consistent error response shape — makes CloudWatch filtering impossible.

## Design

Four layers, adapted from a production FastAPI pattern.

---

### Layer 1 — Exception hierarchy (`app/core/exceptions.py`)

A base `AppException` with class-level defaults for `_status_code`, `_message`, and `_errors`. All values are overridable per-instance, but subclasses can be raised with no arguments and produce a fully-formed error.

```
AppException (base)
├── DocumentNotFoundException      (404) — document doesn't exist or wrong account
├── DocumentNotUploadedException   (409) — document exists but S3 object not present
├── JobNotFoundException           (404) — job doesn't exist or wrong account
├── StorageException               (503) — S3 call failed unexpectedly
├── QueueException                 (503) — RabbitMQ connection or publish failed
└── DatabaseException              (503) — SQLAlchemy error in any repository
```

Auth errors (`401`) stay as `HTTPException` — the HTTP exception handler (Layer 4) reformats them into the same envelope, so no custom class is needed there.

---

### Layer 2 — Raise sites

**`app/services/job.py`**
- Replace `raise ValueError("Document not found")` → `raise DocumentNotFoundException()`
- Replace `raise ValueError("Document has not been uploaded")` → `raise DocumentNotUploadedException()`

**`app/services/artifact.py`**
- Inject `document_repo` into `ArtifactService.__init__` (currently only has `artifact_repo` and `storage`)
- At the top of `list_for_document`, check document existence; if `None`, `raise DocumentNotFoundException()`

**`app/api/routes/jobs.py`**
- Remove `try/except ValueError` entirely
- Replace `if job is None: raise HTTPException(404)` with `get_or_raise(job_service.get(...), JobNotFoundException())`

**`app/infrastructure/storage/s3_client.py`**
- In `object_exists`: the non-404 `ClientError` already re-raises bare — wrap as `raise StorageException() from e`
- In `generate_upload_url` / `generate_download_url`: wrap `ClientError` as `raise StorageException() from e`

**`app/infrastructure/messaging/rabbitmq_client.py`**
- In `enqueue`: wrap `aio_pika` exceptions as `raise QueueException() from e`

**`app/infrastructure/repositories/*.py`**
- In each repository method: wrap `SQLAlchemyError` as `raise DatabaseException() from e`

---

### Layer 3 — Utility helper (`app/core/errors.py`)

```python
async def get_or_raise(awaitable, exception):
    result = await awaitable
    if result is None:
        raise exception
    return result
```

Replaces the repetitive `if result is None: raise X()` pattern in routes.

---

### Layer 4 — Exception handlers (`app/app.py`)

Three handlers registered at startup. All produce the same JSON envelope:

```json
{
  "status": "error",
  "status_code": 404,
  "type": "DocumentNotFoundException",
  "message": "Document not found.",
  "errors": {}
}
```

| Handler | Catches | `status_code` source |
|---|---|---|
| internal handler | `AppException` and all subclasses | `exc.get_status_code()` |
| validation handler | `RequestValidationError` (Pydantic) | `422` |
| http handler | `HTTPException` (auth errors, etc.) | `exc.status_code` |

The validation handler populates `errors` with a field-level dict (e.g. `{"file_name": ["field required"]}`). The other two handlers set `errors` to `{}`.

The `type` field is the exception class name — enables CloudWatch metric filters like `{ $.type = "StorageException" }`.

---

## File Impact

| File | Change |
|---|---|
| `app/core/exceptions.py` | New — exception hierarchy |
| `app/core/errors.py` | New — `get_or_raise` helper |
| `app/app.py` | Add three exception handlers |
| `app/services/job.py` | Replace `ValueError` raises with domain exceptions |
| `app/services/artifact.py` | Inject `document_repo`, add document existence check |
| `app/api/routes/jobs.py` | Remove `try/except ValueError`, use `get_or_raise` |
| `app/infrastructure/storage/s3_client.py` | Wrap `ClientError` as `StorageException` |
| `app/infrastructure/messaging/rabbitmq_client.py` | Wrap `aio_pika` errors as `QueueException` |
| `app/core/providers.py` | Pass `document_repo` when constructing `ArtifactService` |
| `app/infrastructure/repositories/*.py` | Wrap `SQLAlchemyError` as `DatabaseException` |
