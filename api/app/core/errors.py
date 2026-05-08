from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from app.core.exceptions import AppException


async def get_or_raise(
    awaitable: Awaitable[Any], exception: AppException
) -> Any:
    result = await awaitable
    if result is None:
        raise exception
    return result
