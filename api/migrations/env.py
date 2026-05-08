import asyncio
from logging.config import fileConfig

from alembic import context
from app.core.config import get_settings
from app.infrastructure.models import Base
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
target_metadata = Base.metadata


def _run_sync_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(
        url=settings.database_url, poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_run_sync_migrations)
    await connectable.dispose()


asyncio.run(run_migrations_online())
