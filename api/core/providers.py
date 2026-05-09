from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from api.core.container import container
from shared.interfaces.infrastructure.messaging import IMessagingService
from shared.interfaces.infrastructure.storage import IStorageService
from shared.interfaces.repositories.account import IAccountRepository
from shared.interfaces.repositories.artifact import IArtifactRepository
from shared.interfaces.repositories.document import IDocumentRepository
from shared.interfaces.repositories.job import IJobRepository
from shared.interfaces.services.account import IAccountService
from shared.interfaces.services.artifact import IArtifactService
from shared.interfaces.services.document import IDocumentService
from shared.interfaces.services.job import IJobService


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


@lru_cache
def get_account_service() -> IAccountService:
    return container.account_service()


@lru_cache
def get_document_service() -> IDocumentService:
    return container.document_service()


@lru_cache
def get_job_service() -> IJobService:
    return container.job_service()


@lru_cache
def get_artifact_service() -> IArtifactService:
    return container.artifact_service()
