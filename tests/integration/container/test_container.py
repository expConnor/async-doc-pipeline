import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import create_async_engine

from api.core.container import Container
from shared.infrastructure.models import Account


class _Settings:
    """Minimal settings stub for open_session tests."""

    def __init__(self, db_url: str) -> None:
        self.sqlalchemy_engine_props = {"url": db_url}


@pytest.fixture
async def container(async_db_url):
    c = Container(_Settings(async_db_url))
    try:
        yield c
    finally:
        await c._engine.dispose()


async def test_open_session_commits_on_success(container, async_db_url):
    inserted_id = None

    async with container.open_session() as session:
        result = await session.execute(
            insert(Account)
            .values(api_key_hash="open_session_commit_test")
            .returning(Account)
        )
        inserted_id = result.scalar_one().id

    # Verify with a separate connection that the row was committed
    engine = create_async_engine(async_db_url)
    try:
        async with engine.connect() as conn:
            row = await conn.scalar(
                select(Account).where(Account.id == inserted_id)
            )

        assert row is not None

        # Cleanup — db_session rollback does not cover committed data
        async with engine.begin() as conn:
            await conn.execute(delete(Account).where(Account.id == inserted_id))
    finally:
        await engine.dispose()


async def test_open_session_rolls_back_on_exception(container, async_db_url):
    inserted_id = None

    with pytest.raises(RuntimeError, match="deliberate"):
        async with container.open_session() as session:
            result = await session.execute(
                insert(Account)
                .values(api_key_hash="open_session_rollback_test")
                .returning(Account)
            )
            inserted_id = result.scalar_one().id
            raise RuntimeError("deliberate")

    # Verify with a separate connection that the row was NOT committed
    engine = create_async_engine(async_db_url)
    try:
        async with engine.connect() as conn:
            row = await conn.scalar(
                select(Account).where(Account.id == inserted_id)
            )
    finally:
        await engine.dispose()

    assert row is None
