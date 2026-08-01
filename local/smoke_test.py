"""Smoke test the whole document pipeline end to end, COUNT times."""

import asyncio
import csv
import socket
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8080"
ACCOUNTS_CSV = Path(__file__).parent / "accounts.csv"
SAMPLE_PDF = Path(__file__).parent / "sample.pdf"
POLL_INTERVAL_SECONDS = 1
POLL_TIMEOUT_SECONDS = 60

# The API container resolves S3/MinIO via the container-network hostname
# "minio" (see docker-compose.yml's S3_ENDPOINT_URL override), so presigned
# upload URLs the API returns contain that hostname literally. It doesn't
# resolve from the host machine. MinIO's port is published to the host as
# localhost:9000, so redirect just that one hostname to 127.0.0.1 — the
# request still sends "Host: minio:9000" (the header the presigned URL's
# SigV4 signature covers), it just connects to 127.0.0.1 at the TCP level.
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

        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
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

        print(f"[{index}] FAILED: timed out after {POLL_TIMEOUT_SECONDS}s")
        return False
    except httpx.HTTPError as e:
        print(f"[{index}] FAILED: {e}")
        return False


async def _main(count: int) -> int:
    api_key = _load_api_key()
    pdf_bytes = SAMPLE_PDF.read_bytes()

    async with (
        httpx.AsyncClient(
            base_url=BASE_URL, headers={"X-API-Key": api_key}, timeout=30.0
        ) as api_client,
        httpx.AsyncClient(timeout=30.0) as upload_client,
    ):
        results = await asyncio.gather(
            *(
                _run_one(api_client, upload_client, i, pdf_bytes)
                for i in range(1, count + 1)
            )
        )

    passed = sum(results)
    print(f"{passed}/{count} passed")
    return 0 if passed == count else 1


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    sys.exit(asyncio.run(_main(count)))
