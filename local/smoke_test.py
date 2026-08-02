"""Smoke test the whole document pipeline end to end, COUNT times."""

import asyncio
import csv
import itertools
import socket
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8080"
ACCOUNTS_CSV = Path(__file__).parent / "accounts.csv"
SAMPLE_PDF = Path(__file__).parent / "sample.pdf"
POLL_INTERVAL_SECONDS = 1
BASE_POLL_TIMEOUT_SECONDS = 60

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


socket.getaddrinfo = _patched_getaddrinfo


def _load_api_key() -> str:
    with ACCOUNTS_CSV.open() as f:
        return next(csv.DictReader(f))["api_key"]


async def _run_one(
    api_client: httpx.AsyncClient,
    upload_client: httpx.AsyncClient,
    index: int,
    pdf_bytes: bytes,
    poll_timeout_seconds: float,
    queued_counter: itertools.count,
    count: int,
) -> bool:
    start = time.monotonic()
    try:
        response = await api_client.post("/documents")
        response.raise_for_status()
        document = response.json()

        upload_response = await upload_client.put(
            document["upload_url"], content=pdf_bytes
        )
        upload_response.raise_for_status()

        process_response = await api_client.post(
            f"/documents/{document['document_id']}/process", json={}
        )
        process_response.raise_for_status()
        job_id = process_response.json()["id"]

        if next(queued_counter) == count:
            print(f"all {count} documents queued successfully")

        deadline = time.monotonic() + poll_timeout_seconds
        while time.monotonic() < deadline:
            job_response = await api_client.get(f"/jobs/{job_id}")
            job_response.raise_for_status()
            job = job_response.json()

            if job["status"] == "completed":
                elapsed = time.monotonic() - start
                print(f"[{index}] ok ({elapsed:.1f}s)")
                return True
            if job["status"] == "failed":
                print(f"[{index}] FAILED: job failed: {job['error_message']}")
                return False

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        print(f"[{index}] FAILED: timed out after {poll_timeout_seconds:.0f}s")
        return False
    except httpx.HTTPError as e:
        print(f"[{index}] FAILED: {e}")
        return False


async def _main(count: int) -> int:
    start = time.monotonic()
    api_key = _load_api_key()
    pdf_bytes = SAMPLE_PDF.read_bytes()
    # The worker is deliberately serial (prefetch_count=1), so drain time
    # scales linearly with count. Scale the per-iteration timeout with it so
    # a busier machine or larger COUNT doesn't produce false-positive
    # timeouts on an otherwise healthy run.
    poll_timeout_seconds = BASE_POLL_TIMEOUT_SECONDS + count

    async with (
        httpx.AsyncClient(
            base_url=BASE_URL, headers={"X-API-Key": api_key}, timeout=30.0
        ) as api_client,
        httpx.AsyncClient(timeout=30.0) as upload_client,
    ):
        queued_counter = itertools.count(1)
        results = await asyncio.gather(
            *(
                _run_one(
                    api_client,
                    upload_client,
                    i,
                    pdf_bytes,
                    poll_timeout_seconds,
                    queued_counter,
                    count,
                )
                for i in range(1, count + 1)
            ),
            return_exceptions=True,
        )

    for i, result in enumerate(results, start=1):
        if isinstance(result, BaseException):
            print(f"[{i}] FAILED: {result}")

    passed = sum(1 for r in results if r is True)
    total_elapsed = time.monotonic() - start
    print(f"{passed}/{count} passed ({total_elapsed:.1f}s total)")
    return 0 if passed == count else 1


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    sys.exit(asyncio.run(_main(count)))
