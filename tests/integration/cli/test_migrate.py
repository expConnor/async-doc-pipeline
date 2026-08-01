import asyncio

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from cli.commands.setup import migrate

EXPECTED_TABLES = {"accounts", "documents", "jobs", "artifacts"}


@pytest.fixture(scope="module")
def fresh_postgres_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
def fresh_db_url(fresh_postgres_container) -> str:
    url = fresh_postgres_container.get_connection_url()
    return url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://", 1
    ).replace("postgresql://", "postgresql+asyncpg://", 1)


class _Settings:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url


@pytest.fixture(autouse=True)
def patched_settings(mocker, fresh_db_url):
    # env.py imports get_settings from shared.core.config directly, and
    # Alembic re-execs env.py fresh on every command.upgrade() call — the
    # patch has to target the origin, not cli.commands.setup, for it to
    # take effect (and it sidesteps get_settings()'s @lru_cache too, since
    # the function object itself is swapped rather than its cached result).
    mocker.patch(
        "shared.core.config.get_settings",
        return_value=_Settings(fresh_db_url),
    )


def _expected_head() -> str:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    head = script.get_current_head()
    assert head is not None, "no migration files found in shared/migrations"
    return head


async def _alembic_version_rows(db_url: str) -> list[str]:
    engine = create_async_engine(db_url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT version_num FROM alembic_version")
            )
            return [row[0] for row in result]
    finally:
        await engine.dispose()


async def _table_names(db_url: str) -> set[str]:
    engine = create_async_engine(db_url)
    try:
        async with engine.connect() as conn:
            return set(
                await conn.run_sync(
                    lambda sync_conn: inspect(sync_conn).get_table_names()
                )
            )
    finally:
        await engine.dispose()


def test_migrate_upgrade_to_head_creates_expected_schema(fresh_db_url):
    migrate()

    versions = asyncio.run(_alembic_version_rows(fresh_db_url))
    assert versions == [_expected_head()]

    tables = asyncio.run(_table_names(fresh_db_url))
    assert EXPECTED_TABLES.issubset(tables)


def test_migrate_is_idempotent_when_run_twice(fresh_db_url):
    migrate()
    migrate()

    versions = asyncio.run(_alembic_version_rows(fresh_db_url))
    assert versions == [_expected_head()]
