from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...dtos.account import AccountDTO
from ...infrastructure.models import Account
from ...interfaces.repositories.account import IAccountRepository


class AccountRepository(IAccountRepository):
    async def get_by_api_key_hash(
        self, session: AsyncSession, api_key_hash: str
    ) -> AccountDTO | None:
        query = select(Account).where(Account.api_key_hash == api_key_hash)
        if account := await session.scalar(query):
            return self._to_dto(account)
        return None

    @staticmethod
    def _to_dto(model: Account) -> AccountDTO:
        return AccountDTO(id=model.id, api_key_hash=model.api_key_hash)
