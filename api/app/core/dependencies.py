import hashlib
from typing import Annotated

from app.core.providers import (
    get_account_repo,
    get_artifact_repo,
    get_db_session,
    get_document_repo,
    get_job_repo,
    get_messaging_service,
    get_storage_service,
)
from app.core.security import api_key_required
from app.dtos.account import AccountDTO
from app.interfaces.infrastructure.messaging import IMessagingService
from app.interfaces.infrastructure.storage import IStorageService
from app.interfaces.repositories.account import IAccountRepository
from app.interfaces.repositories.artifact import IArtifactRepository
from app.interfaces.repositories.document import IDocumentRepository
from app.interfaces.repositories.job import IJobRepository
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

DBSession = Annotated[AsyncSession, Depends(get_db_session)]
AccountRepo = Annotated[IAccountRepository, Depends(get_account_repo)]
DocumentRepo = Annotated[IDocumentRepository, Depends(get_document_repo)]
JobRepo = Annotated[IJobRepository, Depends(get_job_repo)]
ArtifactRepo = Annotated[IArtifactRepository, Depends(get_artifact_repo)]
MessagingService = Annotated[IMessagingService, Depends(get_messaging_service)]
StorageService = Annotated[IStorageService, Depends(get_storage_service)]


async def get_current_account(
    raw_key: Annotated[str, Depends(api_key_required)],
    session: DBSession,
    account_repo: AccountRepo,
) -> AccountDTO:
    hashed = hashlib.sha256(raw_key.encode()).hexdigest()
    account = await account_repo.get_by_api_key_hash(
        session=session, api_key_hash=hashed
    )
    if account is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return account


CurrentAccount = Annotated[AccountDTO, Depends(get_current_account)]
