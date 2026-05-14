import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from shared.infrastructure.models import Base


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def async_db_url(postgres_container) -> str:
    url = postgres_container.get_connection_url()
    # Replace psycopg2 driver with asyncpg
    return url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://", 1
    ).replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.fixture(scope="session", autouse=True)
def create_schema(async_db_url):
    """Create tables and the partial unique index once per test session."""

    async def _setup():
        engine = create_async_engine(async_db_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS"
                    " one_active_job_per_document"
                    " ON jobs (account_id, document_id)"
                    " WHERE status IN ("
                    "'QUEUED'::job_status_enum,"
                    " 'STARTED'::job_status_enum)"
                )
            )
        await engine.dispose()

    asyncio.run(_setup())


@pytest.fixture
async def db_session(async_db_url) -> AsyncSession:
    """Per-test async session. Rolls back after each test — no data persists."""
    engine = create_async_engine(async_db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()
