from datetime import datetime

import pytest
from sqlalchemy import insert

from shared.dtos.artifact import ArtifactType
from shared.dtos.job import JobStatus
from shared.infrastructure.models import Account, Artifact, Document, Job


@pytest.fixture
async def account(db_session):
    result = await db_session.execute(
        insert(Account).values(api_key_hash="hash_account_a").returning(Account)
    )
    return result.scalar_one()


@pytest.fixture
async def account_b(db_session):
    result = await db_session.execute(
        insert(Account).values(api_key_hash="hash_account_b").returning(Account)
    )
    return result.scalar_one()


@pytest.fixture
async def document(db_session, account):
    result = await db_session.execute(
        insert(Document)
        .values(
            object_key="uploads/test.pdf",
            file_name="test.pdf",
            account_id=account.id,
            created_at=datetime.now(),
        )
        .returning(Document)
    )
    return result.scalar_one()


@pytest.fixture
async def job(db_session, account, document):
    result = await db_session.execute(
        insert(Job)
        .values(
            account_id=account.id,
            document_id=document.id,
            status=JobStatus.QUEUED,
            artifact_types=[ArtifactType.MARKDOWN],
            attempts=0,
            max_attempts=3,
            created_at=datetime.now(),
            queued_at=datetime.now(),
        )
        .returning(Job)
    )
    return result.scalar_one()


@pytest.fixture
async def artifact(db_session, account, document, job):
    result = await db_session.execute(
        insert(Artifact)
        .values(
            job_id=job.id,
            document_id=document.id,
            artifact_type=ArtifactType.MARKDOWN,
            object_key="artifacts/1/test.md",
            created_at=datetime.now(),
        )
        .returning(Artifact)
    )
    return result.scalar_one()
