import contextlib
from collections.abc import AsyncIterator

from app.core.config import get_settings
from app.core.settings.base import BaseAppSettings
from app.infrastructure.messaging.rabbitmq_client import (
    RabbitMQMessagingService,
)
from app.infrastructure.repositories.account import AccountRepository
from app.infrastructure.repositories.artifact import ArtifactRepository
from app.infrastructure.repositories.document import DocumentRepository
from app.infrastructure.repositories.job import JobRepository
from app.infrastructure.storage.s3_client import S3StorageService
from app.interfaces.infrastructure.messaging import IMessagingService
from app.interfaces.infrastructure.storage import IStorageService
from app.interfaces.repositories.account import IAccountRepository
from app.interfaces.repositories.artifact import IArtifactRepository
from app.interfaces.repositories.document import IDocumentRepository
from app.interfaces.repositories.job import IJobRepository
from app.interfaces.services.account import IAccountService
from app.interfaces.services.artifact import IArtifactService
from app.interfaces.services.document import IDocumentService
from app.interfaces.services.job import IJobService
from app.services.account import AccountService
from app.services.artifact import ArtifactService
from app.services.document import DocumentService
from app.services.job import JobService
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


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

    def account_repository(self) -> IAccountRepository:
        return AccountRepository()

    def document_repository(self) -> IDocumentRepository:
        return DocumentRepository()

    def job_repository(self) -> IJobRepository:
        return JobRepository()

    def artifact_repository(self) -> IArtifactRepository:
        return ArtifactRepository()

    def messaging_service(self) -> IMessagingService:
        return RabbitMQMessagingService(url=self._settings.rabbitmq_url)

    def storage_service(self) -> IStorageService:
        return S3StorageService(
            region=self._settings.aws_region,
            bucket=self._settings.s3_bucket,
        )

    def account_service(self) -> IAccountService:
        return AccountService(account_repo=self.account_repository())

    def document_service(self) -> IDocumentService:
        return DocumentService(
            document_repo=self.document_repository(),
            storage=self.storage_service(),
        )

    def job_service(self) -> IJobService:
        return JobService(
            job_repo=self.job_repository(),
            document_repo=self.document_repository(),
            messaging=self.messaging_service(),
            storage=self.storage_service(),
            queue=self._settings.rabbitmq_queue,
        )

    def artifact_service(self) -> IArtifactService:
        return ArtifactService(
            artifact_repo=self.artifact_repository(),
            storage=self.storage_service(),
        )


container = Container(settings=get_settings())
