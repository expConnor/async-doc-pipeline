from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.providers import (
    get_account_service,
    get_artifact_service,
    get_db_session,
    get_document_service,
    get_job_service,
)
from api.core.security import api_key_required
from shared.dtos.account import AccountDTO
from shared.interfaces.services.account import IAccountService
from shared.interfaces.services.artifact import IArtifactService
from shared.interfaces.services.document import IDocumentService
from shared.interfaces.services.job import IJobService

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
