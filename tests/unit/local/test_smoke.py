from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

from pipeline.client import JobFailed
from smoke import Result, _format_result, _run_one

DOC_ID = UUID("11111111-1111-1111-1111-111111111111")
JOB_ID = UUID("22222222-2222-2222-2222-222222222222")


def _document():
    return SimpleNamespace(id=DOC_ID, upload_url="http://x/upload")


async def test_run_one_returns_ok_result_on_success():
    client = AsyncMock()
    client.submit_document.return_value = _document()
    client.start_processing.return_value = JOB_ID
    client.wait_for_completion.return_value = {"status": "completed"}

    result = await _run_one(client, 1, b"pdf-bytes", poll_timeout=5)

    assert result == Result(index=1, ok=True, elapsed=result.elapsed)
    client.upload.assert_awaited_once_with("http://x/upload", b"pdf-bytes")


async def test_run_one_returns_failed_result_on_job_failure():
    client = AsyncMock()
    client.submit_document.return_value = _document()
    client.start_processing.return_value = JOB_ID
    client.wait_for_completion.side_effect = JobFailed(
        {"error_message": "boom"}
    )

    result = await _run_one(client, 2, b"pdf-bytes", poll_timeout=5)

    assert result.ok is False
    assert result.index == 2
    assert "boom" in result.error


async def test_run_one_returns_failed_result_on_timeout():
    client = AsyncMock()
    client.submit_document.return_value = _document()
    client.start_processing.return_value = JOB_ID
    client.wait_for_completion.side_effect = TimeoutError(
        "job did not complete within 5s"
    )

    result = await _run_one(client, 3, b"pdf-bytes", poll_timeout=5)

    assert result.ok is False
    assert "did not complete" in result.error


def test_format_result_ok():
    result = Result(index=1, ok=True, elapsed=1.23)
    assert _format_result(result) == "[1] ok (1.2s)"


def test_format_result_failed():
    result = Result(index=2, ok=False, elapsed=0.5, error="timed out")
    assert _format_result(result) == "[2] FAILED: timed out"
