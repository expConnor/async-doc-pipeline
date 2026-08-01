from datetime import datetime
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import DatabaseException
from ...dtos.artifact import ArtifactDTO, CreateArtifactDTO
from ...infrastructure.models import Artifact, Document
from ...interfaces.repositories.artifact import IArtifactRepository


class ArtifactRepository(IArtifactRepository):
    async def create(
        self, session: AsyncSession, dto: CreateArtifactDTO
    ) -> ArtifactDTO:
        try:
            query = (
                insert(Artifact)
                .values(
                    job_id=dto.job_id,
                    document_id=dto.document_id,
                    artifact_type=dto.artifact_type,
                    object_key=dto.object_key,
                    created_at=datetime.now(),
                )
                .returning(Artifact)
            )
            result = await session.execute(query)
            return self._to_dto(result.scalar_one())
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    async def list_by_document_id(
        self, session: AsyncSession, document_id: UUID, account_id: int
    ) -> list[ArtifactDTO]:
        try:
            query = (
                select(Artifact)
                .join(Document, Artifact.document_id == Document.id)
                .where(
                    Artifact.document_id == document_id,
                    Document.account_id == account_id,
                )
            )
            result = await session.scalars(query)
            return [self._to_dto(a) for a in result]
        except SQLAlchemyError as e:
            raise DatabaseException() from e

    @staticmethod
    def _to_dto(model: Artifact) -> ArtifactDTO:
        return ArtifactDTO(
            id=model.id,
            job_id=model.job_id,
            document_id=model.document_id,
            artifact_type=model.artifact_type,
            object_key=model.object_key,
            created_at=model.created_at,
        )
