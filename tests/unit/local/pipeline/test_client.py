from pathlib import Path
from uuid import UUID

import httpx
import pytest
from pipeline.client import BackpressureRejected, JobFailed, PipelineClient

DOC_ID = "11111111-1111-1111-1111-111111111111"
JOB_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def accounts_csv(tmp_path: Path) -> Path:
    path = tmp_path / "accounts.csv"
    path.write_text("account_id,api_key\n1,test-key\n")
    return path


async def test_submit_document_parses_response(accounts_csv):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/documents"
        assert request.headers["X-API-Key"] == "test-key"
        return httpx.Response(
            201,
            json={"document_id": DOC_ID, "upload_url": "http://minio/upload"},
        )

    transport = httpx.MockTransport(handler)
    async with PipelineClient(
        accounts_csv=accounts_csv, transport=transport
    ) as client:
        doc = await client.submit_document()

    assert doc.id == UUID(DOC_ID)
    assert doc.upload_url == "http://minio/upload"


async def test_upload_puts_bytes_to_presigned_url(accounts_csv):
    received = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received["content"] = request.content
        received["url"] = str(request.url)
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    async with PipelineClient(
        accounts_csv=accounts_csv, transport=transport
    ) as client:
        await client.upload("http://minio/upload-path", b"pdf-bytes")

    assert received["content"] == b"pdf-bytes"
    assert received["url"] == "http://minio/upload-path"


async def test_start_processing_returns_job_id(accounts_csv):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/documents/{DOC_ID}/process"
        return httpx.Response(201, json={"id": JOB_ID, "status": "queued"})

    transport = httpx.MockTransport(handler)
    async with PipelineClient(
        accounts_csv=accounts_csv, transport=transport
    ) as client:
        job_id = await client.start_processing(UUID(DOC_ID))

    assert job_id == UUID(JOB_ID)


async def test_start_processing_raises_backpressure_rejected_on_429(
    accounts_csv,
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "Queue capacity exceeded."})

    transport = httpx.MockTransport(handler)
    async with PipelineClient(
        accounts_csv=accounts_csv, transport=transport
    ) as client:
        with pytest.raises(BackpressureRejected):
            await client.start_processing(UUID(DOC_ID))


async def test_wait_for_completion_returns_job_once_completed(accounts_csv):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        status = "started" if calls["n"] == 1 else "completed"
        return httpx.Response(
            200, json={"id": JOB_ID, "status": status, "error_message": None}
        )

    transport = httpx.MockTransport(handler)
    async with PipelineClient(
        accounts_csv=accounts_csv, transport=transport
    ) as client:
        job = await client.wait_for_completion(
            UUID(JOB_ID), timeout=5, poll_interval=0
        )

    assert job["status"] == "completed"
    assert calls["n"] == 2


async def test_wait_for_completion_raises_job_failed(accounts_csv):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": JOB_ID, "status": "failed", "error_message": "boom"},
        )

    transport = httpx.MockTransport(handler)
    async with PipelineClient(
        accounts_csv=accounts_csv, transport=transport
    ) as client:
        with pytest.raises(JobFailed) as exc_info:
            await client.wait_for_completion(
                UUID(JOB_ID), timeout=5, poll_interval=0
            )

    assert exc_info.value.job["error_message"] == "boom"


async def test_wait_for_completion_times_out(accounts_csv):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": JOB_ID, "status": "started"})

    transport = httpx.MockTransport(handler)
    async with PipelineClient(
        accounts_csv=accounts_csv, transport=transport
    ) as client:
        with pytest.raises(TimeoutError):
            await client.wait_for_completion(
                UUID(JOB_ID), timeout=0.05, poll_interval=0.01
            )
