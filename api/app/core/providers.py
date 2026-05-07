from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from app.core.container import container
from app.interfaces.infrastructure.messaging import IMessagingService
from app.interfaces.infrastructure.storage import IStorageService
from app.interfaces.repositories.account import IAccountRepository
from app.interfaces.repositories.artifact import IArtifactRepository
from app.interfaces.repositories.document import IDocumentRepository
from app.interfaces.repositories.job import IJobRepository
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with container.open_session() as session:
        yield session


@lru_cache
def get_account_repo() -> IAccountRepository:
    return container.account_repository()


@lru_cache
def get_document_repo() -> IDocumentRepository:
    return container.document_repository()


@lru_cache
def get_job_repo() -> IJobRepository:
    return container.job_repository()


@lru_cache
def get_artifact_repo() -> IArtifactRepository:
    return container.artifact_repository()


@lru_cache
def get_messaging_service() -> IMessagingService:
    return container.messaging_service()


@lru_cache
def get_storage_service() -> IStorageService:
    return container.storage_service()
