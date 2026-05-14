import pytest

from worker.infrastructure.messaging.consumer import RabbitMQConsumer
from worker.services.processing_service import ProcessingService


@pytest.fixture
def job_repo(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def document_repo(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def artifact_repo(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def storage(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def parser(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def messaging(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def processing_service(job_repo, document_repo, artifact_repo, storage, parser):
    return ProcessingService(
        job_repo=job_repo,
        document_repo=document_repo,
        artifact_repo=artifact_repo,
        storage=storage,
        parser=parser,
    )


@pytest.fixture
def container(mocker, session):
    c = mocker.MagicMock()
    cm = mocker.MagicMock()
    cm.__aenter__ = mocker.AsyncMock(return_value=session)
    cm.__aexit__ = mocker.AsyncMock(return_value=False)
    c.open_session.return_value = cm
    return c


@pytest.fixture
def consumer(container, processing_service, messaging, job_repo):
    return RabbitMQConsumer(
        container=container,
        processing_service=processing_service,
        messaging=messaging,
        job_repo=job_repo,
        url="amqp://localhost/",
        queue="jobs",
    )
