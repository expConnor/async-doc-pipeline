from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
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
            base_stmt = insert(Artifact).values(
                job_id=dto.job_id,
                document_id=dto.document_id,
                artifact_type=dto.artifact_type,
                object_key=dto.object_key,
                created_at=datetime.now(),
            )
            stmt = base_stmt.on_conflict_do_update(
                index_elements=["document_id", "artifact_type"],
                set_={
                    "job_id": base_stmt.excluded.job_id,
                    "object_key": base_stmt.excluded.object_key,
                },
            ).returning(Artifact)
            result = await session.execute(
                stmt, execution_options={"populate_existing": True}
            )
            artifact = result.scalar_one()
            return self._to_dto(artifact)
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
