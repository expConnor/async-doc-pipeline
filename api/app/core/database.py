from collections.abc import AsyncIterator

from app.core.config import get_settings
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_settings = get_settings()
_engine = create_async_engine(**_settings.sqlalchemy_engine_props)
_session_factory = async_sessionmaker(bind=_engine, expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    session = _session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
