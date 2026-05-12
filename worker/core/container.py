import contextlib
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.core.config import get_settings
from shared.core.settings.base import BaseAppSettings
from shared.infrastructure.messaging.rabbitmq_client import (
    RabbitMQMessagingService,
)
from shared.infrastructure.repositories.artifact import ArtifactRepository
from shared.infrastructure.repositories.document import DocumentRepository
from shared.infrastructure.repositories.job import JobRepository
from shared.infrastructure.storage.s3_client import S3StorageService
from shared.interfaces.infrastructure.messaging import IMessagingService
from shared.interfaces.infrastructure.storage import IStorageService
from shared.interfaces.repositories.artifact import IArtifactRepository
from shared.interfaces.repositories.document import IDocumentRepository
from shared.interfaces.repositories.job import IJobRepository

from ..infrastructure.messaging.consumer import RabbitMQConsumer
from ..infrastructure.parsing.pymupdf_parser import PyMuPDFParser
from ..interfaces.parser import IDocumentParser
from ..services.processing_service import ProcessingService


class Container:
    def __init__(self, settings: BaseAppSettings) -> None:
        self._settings = settings
        self._engine = create_async_engine(**settings.sqlalchemy_engine_props)
        self._session_factory = async_sessionmaker(
            bind=self._engine, expire_on_commit=False
        )

    @contextlib.asynccontextmanager
    async def open_session(self) -> AsyncIterator[AsyncSession]:
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    def job_repository(self) -> IJobRepository:
        return JobRepository()

    def artifact_repository(self) -> IArtifactRepository:
        return ArtifactRepository()

    def document_repository(self) -> IDocumentRepository:
        return DocumentRepository()

    def storage_service(self) -> IStorageService:
        return S3StorageService(
            region=self._settings.aws_region,
            bucket=self._settings.s3_bucket,
        )

    def parser(self) -> IDocumentParser:
        return PyMuPDFParser()

    def messaging_service(self) -> IMessagingService:
        return RabbitMQMessagingService(url=self._settings.rabbitmq_url)

    def processing_service(self) -> ProcessingService:
        return ProcessingService(
            job_repo=self.job_repository(),
            document_repo=self.document_repository(),
            artifact_repo=self.artifact_repository(),
            storage=self.storage_service(),
            parser=self.parser(),
        )

    def consumer(self) -> RabbitMQConsumer:
        return RabbitMQConsumer(
            container=self,
            processing_service=self.processing_service(),
            messaging=self.messaging_service(),
            job_repo=self.job_repository(),
            url=self._settings.rabbitmq_url,
            queue=self._settings.rabbitmq_queue,
        )


container = Container(settings=get_settings())
