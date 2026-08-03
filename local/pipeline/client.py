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


# This function "monkeypatches" socket.getaddrinfo — Python lets you reassign
# a function at runtime, even one from the standard library. socket.getaddrinfo
# is the function every network call in Python eventually goes through to turn
# a hostname into an IP address (DNS resolution). Here we're not editing that
# function's source code — we're swapping out what the name `socket.getaddrinfo`
# points to, for the lifetime of `with PipelineClient()`. `_real_getaddrinfo`
# above is a saved reference to the original, so this wrapper can still do a
# real lookup for every hostname except "minio".
def _patched_getaddrinfo(host, *args, **kwargs):
    if host == "minio" or host == b"minio":
        host = "localhost"
    return _real_getaddrinfo(host, *args, **kwargs)


# @dataclass is a decorator (a function that wraps another and changes its
# behavior) that auto-generates the boilerplate a plain data-holding class
# would otherwise need by hand: __init__ (so `Document(id=..., upload_url=...)`
# works), __repr__ (a readable string when you print one), and __eq__ (so two
# Documents with the same fields compare equal). `frozen=True` makes instances
# read-only after creation — assigning to `doc.id` later raises an error. This
# is appropriate here because a Document is just a snapshot of an API response;
# nothing should be mutating it after the fact.
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


# PipelineClient is an "async context manager" — the async version of the
# object behind Python's `with` statement. Defining __aenter__ and __aexit__
# lets code write `async with PipelineClient() as client:` and be guaranteed
# __aexit__ runs on the way out, even if an exception happens inside the
# `with` block. That guarantee is the whole reason this class exists as a
# context manager rather than a function: __aenter__ patches
# socket.getaddrinfo and opens two httpx clients, and __aexit__ must always
# undo the patch and close those clients — a scenario that crashes halfway
# through must not leave the DNS patch active for the rest of the process.
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
        # `httpx.AsyncClient | None` is a type hint meaning "this attribute is
        # either an AsyncClient or the value None". It starts as None here in
        # __init__ because the real client isn't created until __aenter__ runs
        # — declaring the type up front just tells readers (and type checkers)
        # what to expect it to become.
        self._api: httpx.AsyncClient | None = None
        self._upload: httpx.AsyncClient | None = None
        self._original_getaddrinfo = socket.getaddrinfo

    # `async def` marks this as a coroutine function — calling it doesn't run
    # the body immediately, it returns an awaitable that the caller must
    # `await` (or, as here, that Python awaits automatically as part of
    # `async with`). This whole codebase uses async/await because the API
    # calls (`self._api.post(...)`, `self._api.get(...)`) are I/O: while
    # waiting on the network, `await` lets other work run instead of blocking
    # the whole program on that wait — this matters in smoke.py, where dozens
    # of documents are submitted concurrently.
    async def __aenter__(self) -> "PipelineClient":
        self._original_getaddrinfo = socket.getaddrinfo
        # Load API key before patching — if this fails, patch stays inactive.
        api_key = self._load_api_key()
        # Patch socket.getaddrinfo for client creation and usage.
        socket.getaddrinfo = _patched_getaddrinfo
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

    # Python calls __aexit__ automatically when the `async with` block ends —
    # whether it ended normally or via an exception. If an exception caused
    # the exit, Python passes its type, the exception object, and its
    # traceback (a TracebackType, the object holding "which line, which call
    # stack" info) in these three parameters; on a normal exit all three are
    # None. This method ignores them (doesn't re-raise or inspect them) — it
    # only cares about running cleanup either way, so it doesn't need to
    # distinguish the two cases.
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        socket.getaddrinfo = self._original_getaddrinfo
        # These two `assert` calls aren't validating user input — they're
        # telling both the reader and the type checker "these are never None
        # by the time __aexit__ runs, because __aenter__ always sets them
        # first". Without them, `self._api` still has the `AsyncClient | None`
        # type from __init__, and calling `.aclose()` on a possibly-None value
        # would be flagged as a type error even though it can't actually
        # happen in practice.
        assert self._api is not None
        assert self._upload is not None
        await self._api.aclose()
        await self._upload.aclose()

    def _load_api_key(self) -> str:
        # csv.DictReader reads each row of a CSV file as a dict keyed by the
        # header row's column names (so `row["api_key"]` instead of tracking
        # a column index). `next(...)` grabs just the first row — this file is
        # expected to have exactly one seeded account (see `make seed`).
        with self._accounts_csv.open() as f:
            return next(csv.DictReader(f))["api_key"]

    async def submit_document(self) -> Document:
        assert self._api is not None
        response = await self._api.post("/documents")
        # raise_for_status() raises an exception if the HTTP status code is
        # 4xx/5xx (an error), and does nothing if it's 2xx (success) — a
        # one-line way to fail loudly instead of silently continuing with an
        # error response as if it were valid data.
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
