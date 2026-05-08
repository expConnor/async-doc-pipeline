from __future__ import annotations

from collections.abc import Awaitable

from app.core.exceptions import AppException


async def get_or_raise[T](
    awaitable: Awaitable[T | None], exception: AppException
) -> T:
    result = await awaitable
    if result is None:
        raise exception
    return result
