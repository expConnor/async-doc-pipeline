from typing import Annotated

from app.core.providers import (
    get_account_service,
    get_artifact_service,
    get_db_session,
    get_document_service,
    get_job_service,
)
from app.core.security import api_key_required
from app.dtos.account import AccountDTO
from app.interfaces.services.account import IAccountService
from app.interfaces.services.artifact import IArtifactService
from app.interfaces.services.document import IDocumentService
from app.interfaces.services.job import IJobService
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

DBSession = Annotated[AsyncSession, Depends(get_db_session)]
AccountServiceDep = Annotated[IAccountService, Depends(get_account_service)]
DocumentServiceDep = Annotated[IDocumentService, Depends(get_document_service)]
JobServiceDep = Annotated[IJobService, Depends(get_job_service)]
ArtifactServiceDep = Annotated[IArtifactService, Depends(get_artifact_service)]


async def get_current_account(
    raw_key: Annotated[str, Depends(api_key_required)],
    session: DBSession,
    account_service: AccountServiceDep,
) -> AccountDTO:
    account = await account_service.authenticate(session, raw_key)
    if account is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return account


CurrentAccount = Annotated[AccountDTO, Depends(get_current_account)]
