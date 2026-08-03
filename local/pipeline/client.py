"""PipelineClient: submit, upload, process, poll — the same flow the smoke
test and every scenario need against the live API.
"""

import asyncio
import csv
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from uuid import UUID

import httpx

BASE_URL = "http://localhost:8080"
ACCOUNTS_CSV = Path(__file__).parent.parent / "accounts.csv"

# The API container resolves S3/MinIO via the container-network hostname
# "minio" (see docker-compose.yml's S3_ENDPOINT_URL override), so presigned
# upload URLs the API returns contain that hostname literally. It doesn't
# resolve from the host machine. MinIO's port is published to the host as
# localhost:9000, so redirect just that one hostname to localhost — the
# request still sends "Host: minio:9000" (the header the presigned URL's
# SigV4 signature covers), it just connects to localhost at the TCP level.
# Both the str and bytes forms are checked because httpx resolves through
# anyio, which passes the hostname as bytes to socket.getaddrinfo (confirmed
# empirically — a str-only check does not catch it and the upload fails with
# a DNS error).
_real_getaddrinfo = socket.getaddrinfo


def _patched_getaddrinfo(host, *args, **kwargs):
    if host == "minio" or host == b"minio":
        host = "localhost"
    return _real_getaddrinfo(host, *args, **kwargs)


@dataclass(frozen=True)
class Document:
    id: UUID
    upload_url: str


class BackpressureRejected(Exception):
    """Raised when the API returns 429 for a /process request."""


class JobFailed(Exception):
    def __init__(self, job: dict) -> None:
        self.job = job
        super().__init__(job.get("error_message"))


class PipelineClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        accounts_csv: Path = ACCOUNTS_CSV,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._accounts_csv = accounts_csv
        self._transport = transport
        self._api: httpx.AsyncClient | None = None
        self._upload: httpx.AsyncClient | None = None
        self._original_getaddrinfo = socket.getaddrinfo

    async def __aenter__(self) -> "PipelineClient":
        self._original_getaddrinfo = socket.getaddrinfo
        socket.getaddrinfo = _patched_getaddrinfo
        api_key = self._load_api_key()
        self._api = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"X-API-Key": api_key},
            timeout=30.0,
            transport=self._transport,
        )
        self._upload = httpx.AsyncClient(
            timeout=30.0, transport=self._transport
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        socket.getaddrinfo = self._original_getaddrinfo
        assert self._api is not None
        assert self._upload is not None
        await self._api.aclose()
        await self._upload.aclose()

    def _load_api_key(self) -> str:
        with self._accounts_csv.open() as f:
            return next(csv.DictReader(f))["api_key"]

    async def submit_document(self) -> Document:
        assert self._api is not None
        response = await self._api.post("/documents")
        response.raise_for_status()
        body = response.json()
        return Document(
            id=UUID(body["document_id"]), upload_url=body["upload_url"]
        )

    async def upload(self, upload_url: str, pdf_bytes: bytes) -> None:
        assert self._upload is not None
        response = await self._upload.put(upload_url, content=pdf_bytes)
        response.raise_for_status()

    async def start_processing(self, document_id: UUID) -> UUID:
        assert self._api is not None
        response = await self._api.post(
            f"/documents/{document_id}/process", json={}
        )
        if response.status_code == 429:
            raise BackpressureRejected()
        response.raise_for_status()
        return UUID(response.json()["id"])

    async def wait_for_completion(
        self, job_id: UUID, timeout: float, poll_interval: float = 1.0
    ) -> dict:
        assert self._api is not None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = await self._api.get(f"/jobs/{job_id}")
            response.raise_for_status()
            job = response.json()
            if job["status"] == "completed":
                return job
            if job["status"] == "failed":
                raise JobFailed(job)
            await asyncio.sleep(poll_interval)
        raise TimeoutError(f"job {job_id} did not complete within {timeout}s")
