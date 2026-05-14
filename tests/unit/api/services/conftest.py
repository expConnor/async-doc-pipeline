import pytest

from api.services.account import AccountService
from api.services.artifact import ArtifactService
from api.services.document import DocumentService
from api.services.job import JobService


@pytest.fixture
def account_repo(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def document_repo(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def job_repo(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def artifact_repo(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def storage(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def messaging(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def account_service(account_repo):
    return AccountService(account_repo)


@pytest.fixture
def document_service(document_repo, storage):
    return DocumentService(document_repo, storage)


@pytest.fixture
def job_service(job_repo, document_repo, messaging, storage):
    return JobService(
        job_repo,
        document_repo,
        messaging,
        storage,
        queue="jobs",
        backpressure_threshold=10,
    )


@pytest.fixture
def artifact_service(artifact_repo, storage, document_repo):
    return ArtifactService(artifact_repo, storage, document_repo)
