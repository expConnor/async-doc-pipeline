from datetime import datetime

from sqlalchemy import insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import DatabaseException
from ...dtos.document import CreateDocumentDTO, DocumentDTO
from ...infrastructure.models import Document
from ...interfaces.repositories.document import IDocumentRepository


class DocumentRepository(IDocumentRepository):
    async def create(
        self, session: AsyncSession, dto: CreateDocumentDTO
    ) -> DocumentDTO:
        try:
            query = (
                insert(Document)
                .values(
                    object_key=dto.object_key,
                    account_id=dto.account_id,
                    created_at=datetime.now(),
                )
                .returning(Document)
            )
            result = await session.execute(query)
            return self._to_dto(result.scalar_one())
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    async def get_by_id(
        self, session: AsyncSession, document_id: int, account_id: int
    ) -> DocumentDTO | None:
        try:
            query = select(Document).where(
                Document.id == document_id,
                Document.account_id == account_id,
            )
            if document := await session.scalar(query):
                return self._to_dto(document)
            return None
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    @staticmethod
    def _to_dto(model: Document) -> DocumentDTO:
        return DocumentDTO(
            id=model.id,
            object_key=model.object_key,
            account_id=model.account_id,
            created_at=model.created_at,
        )
