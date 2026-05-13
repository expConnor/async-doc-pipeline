import json

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from shared.core.config import get_settings
from shared.core.exceptions import AppException
from shared.core.logging import setup_logging
from shared.core.settings.base import AppEnvTypes

_settings = get_settings()
setup_logging(json_logs=_settings.app_env == AppEnvTypes.production)

from api.middleware import LoggingMiddleware  # noqa: E402
from api.routes import documents, health, jobs  # noqa: E402

logger = structlog.get_logger()
app = FastAPI()

app.add_middleware(LoggingMiddleware)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(jobs.router)


def _error_body(
    status_code: int, type_: str, message: str, errors: dict
) -> dict:
    return {
        "status": "error",
        "status_code": status_code,
        "type": type_,
        "message": message,
        "errors": errors,
    }


@app.exception_handler(AppException)
async def internal_exception_handler(
    request: Request, exc: AppException
) -> JSONResponse:
    status_code = exc.get_status_code()
    if status_code >= 500:
        logger.error(
            "app.exception",
            exc_type=type(exc).__name__,
            status_code=status_code,
            exc_info=exc,
        )
    else:
        logger.warning(
            "app.exception",
            exc_type=type(exc).__name__,
            status_code=status_code,
        )
    return JSONResponse(
        status_code=status_code,
        content=_error_body(
            status_code=status_code,
            type_=type(exc).__name__,
            message=exc.get_message(),
            errors=exc.get_errors(),
        ),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    if isinstance(exc.detail, str):
        message = exc.detail
    else:
        message = json.dumps(exc.detail)
    logger.warning(
        "http.exception",
        status_code=exc.status_code,
        detail=message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(
            status_code=exc.status_code,
            type_="HTTPException",
            message=message,
            errors={},
        ),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors: dict[str, list[str]] = {}
    for error in exc.errors():
        field = str(error["loc"][-1]) if error["loc"] else "body"
        msg = error.get("ctx", {}).get("reason") or error["msg"]
        errors.setdefault(field, []).append(msg.lower())
    logger.warning("request.validation_error", errors=errors)
    return JSONResponse(
        status_code=422,
        content=_error_body(
            status_code=422,
            type_="RequestValidationError",
            message="Request validation failed.",
            errors=errors,
        ),
    )
