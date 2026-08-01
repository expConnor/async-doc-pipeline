# Smoke test script

## Purpose

A single command, `make run COUNT=100`, that exercises the full document
pipeline (API → S3/MinIO → RabbitMQ → worker → RDS) end to end, N times, and
reports how many succeeded. Used to sanity-check that a local stack (after
`make setup`, or after a code change) actually works, not just that
individual services pass their unit/integration tests.

## The MinIO hostname problem

The API's S3 client is configured (via `docker-compose.yml`) with
`S3_ENDPOINT_URL=http://minio:9000` — the container-network name for the
MinIO service. Presigned upload URLs the API returns therefore contain the
literal hostname `minio`, which only resolves inside Docker's internal
network. A request from the host machine to that URL fails outright (DNS
lookup error).

The URL's signature (SigV4) covers the `Host` header, so the fix can't be a
string replace on the URL (`minio` → `localhost`) — that would change what
was signed and MinIO would reject the request with a signature mismatch.

Verified fix: patch `socket.getaddrinfo` for the duration of the script so
that lookups for the hostname `minio` resolve to `127.0.0.1` (MinIO's port
9000 is already published to the host by docker-compose). The outgoing
request still carries `Host: minio:9000` — exactly what was signed — it
simply connects to `127.0.0.1:9000` at the TCP level. This was tested against
the running local stack and confirmed working (worker logs showed the
uploaded object fetched with the correct byte size). The patch is local to
the script's process and does not touch `/etc/hosts` or system DNS.

## Script: `local/smoke_test.py`

Run via `poetry run python local/smoke_test.py $(COUNT)` (positional arg,
default 1 if omitted). Uses `httpx` (already a dev dependency) for HTTP and
`asyncio` for concurrency.

**Setup (once):**
- Apply the `socket.getaddrinfo` patch described above.
- Read `local/accounts.csv`, take the first row's `api_key`.
- Read `local/sample.pdf` (a small, real, committed one-page PDF — generated
  once with PyMuPDF so the worker's parser can open it successfully) into
  memory.
- Base URL: `http://localhost:8080` (matches docker-compose's published API
  port).

**Per iteration** (runs as one `asyncio` task, all `COUNT` tasks started
together via `asyncio.gather`):
1. `POST /documents` with the API key header → get `document_id`,
   `upload_url`.
2. `PUT` the sample PDF bytes to `upload_url`.
3. `POST /documents/{document_id}/process` with an empty body → get `job_id`.
4. Poll `GET /jobs/{job_id}` every 1s, up to 60s total, until `status` is
   `"completed"` or `"failed"` (lowercase — confirmed these are the actual
   JSON values, from `shared/dtos/job.py`'s `JobStatus` enum).
5. Return a result: pass if `status == "completed"`; otherwise a failure
   reason (`"failed: <error_message>"`, `"timed out after 60s"`, or the
   exception message if any HTTP call raised).

Each task prints its own one-line result the moment it finishes (e.g.
`[42] ok (0.8s)` or `[7] FAILED: timed out after 60s`) — output order isn't
sequential since tasks run concurrently. After all tasks finish, print a
summary line (`"97/100 passed"`) and exit with code 1 if any iteration
failed, 0 if all passed.

**60s per-job timeout sizing:** the worker processes one job at a time
(`prefetch_count=1`), but a measured real run showed ~200–500ms per job for
a one-page PDF. Even fully serialized, 100 jobs is 100 × ~500ms = ~50s in the
worst case — close to, not "well under," a fixed 60s timeout, leaving only
~10s of margin at `COUNT=100`. A live `COUNT=100` run confirmed this: the
slowest iteration finished at 47.8s. Since the worker is serial, drain time
scales linearly with `COUNT` while a fixed timeout doesn't, so the timeout
now scales with it: `POLL_TIMEOUT_SECONDS = 60 + count`, giving every run a
consistent ~60s of margin regardless of size.

## `local/sample.pdf`

A small, real, valid one-page PDF, generated once via PyMuPDF (`fitz`) and
committed to the repo (not regenerated at runtime) — the worker's parser
needs actual valid PDF bytes to succeed, not arbitrary bytes.

## Makefile

```makefile
run:         ## Smoke test the whole system end-to-end. Usage: make run COUNT=100
	poetry run python local/smoke_test.py $(COUNT)
```

Reuses the existing `COUNT ?= 1` default already in the Makefile (used by
`seed`).

## Out of scope

- Fetching the artifact download URL / verifying Markdown content (explicitly
  excluded per requirements — polling the job to completion is enough).
- Load testing / throughput measurement beyond "does it work N times."
- Cleanup of created documents/jobs/S3 objects — left in place, same as any
  other local dev activity.
