from app.api.middleware import LoggingMiddleware
from app.api.routes import documents, health, jobs
from app.core.exceptions import AppException
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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
    return JSONResponse(
        status_code=exc.get_status_code(),
        content=_error_body(
            status_code=exc.get_status_code(),
            type_=type(exc).__name__,
            message=exc.get_message(),
            errors=exc.get_errors(),
        ),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(
            status_code=exc.status_code,
            type_="HTTPException",
            message=detail,
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
    return JSONResponse(
        status_code=422,
        content=_error_body(
            status_code=422,
            type_="RequestValidationError",
            message="Request validation failed.",
            errors=errors,
        ),
    )
