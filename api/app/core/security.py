from fastapi import HTTPException, Request
from fastapi.security import APIKeyHeader as _APIKeyHeader


class APIKeyHeader(_APIKeyHeader):
    def __init__(self, raise_error: bool = True, **kwargs) -> None:
        super().__init__(name="X-API-KEY", **kwargs)
        self._raise_error = raise_error

    async def __call__(self, request: Request) -> str | None:
        key = request.headers.get("X-API-KEY")
        if not key:
            if not self._raise_error:
                return None
            raise HTTPException(
                status_code=401, detail="Missing X-API-KEY header"
            )
        return key


api_key_required = APIKeyHeader(raise_error=True)
api_key_optional = APIKeyHeader(raise_error=False)
