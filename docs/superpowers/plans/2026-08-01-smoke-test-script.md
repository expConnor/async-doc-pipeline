# Smoke Test Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `make run COUNT=100` — a script that exercises the full document pipeline (API → S3/MinIO → RabbitMQ → worker → RDS) end to end, `COUNT` times concurrently, and reports a pass/fail summary.

**Architecture:** A single standalone script, `local/smoke_test.py`, run via `poetry run python local/smoke_test.py <count>` (no new package, no new dependency — `httpx` is already a dev dependency). It reads the seeded account's API key from `local/accounts.csv` and uploads a small committed sample PDF (`local/sample.pdf`) on each iteration. A `run` target in the root `Makefile` wires it to `make run COUNT=100`, reusing the `COUNT` variable that already exists there for `make seed`.

**Tech Stack:** Python 3.13, `httpx.AsyncClient` + `asyncio.gather` for concurrent iterations, `csv` (stdlib) for reading the account key, `socket.getaddrinfo` monkeypatch (stdlib) to work around a Docker-network hostname that doesn't resolve from the host.

## Global Constraints

- `local/` is entirely gitignored (`.gitignore:61`, currently just `local/`). A
  plain `git add local/<file>` on any path under it is silently blocked
  ("The following paths are ignored..."). Because the ignore pattern excludes
  the *directory itself*, per-file negation (`!local/sample.pdf`) does not
  work — git never descends into an excluded directory to check it (verified
  empirically). The fix is to change the pattern from `local/` to `local/*`
  (excludes the directory's *contents* by default, not the directory), then
  add negations for the specific files that must be tracked. Task 1, Step 0
  makes this change once, covering both new tracked files
  (`local/sample.pdf` from Task 1, `local/smoke_test.py` from Task 2).
  `local/accounts.csv` must remain ignored (it holds a live API key) — do not
  add a negation for it.
- No new dependencies — `httpx` is already declared under `[tool.poetry.group.dev.dependencies]` in `pyproject.toml` and is installed in the host Poetry environment used to run this script.
- Job status values returned by the API are lowercase strings (`"queued"`, `"started"`, `"completed"`, `"failed"`) — confirmed from `shared/dtos/job.py`'s `JobStatus(StrEnum)`. Do not compare against uppercase.
- The script must not fetch the artifact download URL — reaching a terminal job status (`completed`/`failed`) is the full scope, per the approved design spec (`docs/superpowers/specs/2026-08-01-smoke-test-script-design.md`).
- Verification for this feature is "run it against the live local stack and read the output," not `pytest` — this script's entire purpose is exercising real infrastructure (API, MinIO, RabbitMQ, worker, Postgres) end to end; there is no meaningful way to unit-test it without mocking away the exact thing it exists to check. The existing `docker compose` stack (started by `make setup`) must be running for both tasks' verification steps.

---

### Task 1: Commit a real sample PDF for the script to upload

**Files:**
- Create: `local/sample.pdf`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: a file at `local/sample.pdf` that Task 2's script reads via `Path(__file__).parent / "sample.pdf"`; a `.gitignore` change that Task 2 relies on to commit `local/smoke_test.py`.

**Why a committed file instead of generating one at runtime:** the worker's PDF parser (PyMuPDF4LLM) needs real, valid PDF bytes to succeed — arbitrary bytes would make every smoke-test iteration fail on the parse step, not exercise the happy path. Generating it once and committing it is simpler than adding PDF-generation logic to the script itself (which would need `fitz`/PyMuPDF as a runtime import just to build a throwaway one-pager).

- [ ] **Step 0: Fix `.gitignore` so the two new files under `local/` can be tracked**

`local/` (`.gitignore:61`) currently ignores the whole directory, which blocks `git add` on anything inside it and can't be selectively undone with `!` negations (git doesn't descend into an excluded directory at all). Replace line 61:

```
local/
```

with:

```
local/*
!local/sample.pdf
!local/smoke_test.py
```

`local/*` ignores the directory's contents by default (instead of the directory itself), so the two negations can un-ignore just these files. `local/accounts.csv` (holds a live local API key) stays ignored.

Verify: `git check-ignore -v local/accounts.csv` still reports it ignored; `git status` (after Step 3 below creates `local/sample.pdf`) shows it as a trackable new file, not ignored.

- [ ] **Step 1: Confirm the local stack is running**

Run: `docker compose ps`
Expected: `api`, `worker`, `postgres`, `rabbitmq`, `minio` all show `Up` (or `Up (healthy)`). If not running, run `make setup` first (out of scope for this plan — it's a precondition).

- [ ] **Step 2: Generate the sample PDF**

`pymupdf4llm` (and therefore `fitz`/PyMuPDF) is already installed in the host Poetry environment as part of the `worker` dependency group. Run:

```bash
poetry run python -c "
import fitz
doc = fitz.open()
page = doc.new_page()
page.insert_text((72, 72), 'Smoke test PDF')
doc.save('local/sample.pdf')
"
```

- [ ] **Step 3: Verify it's a valid, parseable one-page PDF**

Run: `poetry run python -c "import fitz; d = fitz.open('local/sample.pdf'); print(d.page_count, 'page(s)')"`
Expected: `1 page(s)`

- [ ] **Step 4: Commit**

```bash
git add .gitignore local/sample.pdf
git commit -m "test: add sample PDF fixture for smoke test script"
```

---

### Task 2: Write the smoke test script and wire `make run`

**Files:**
- Create: `local/smoke_test.py`
- Modify: `Makefile` (add `run` target and add `run` to `.PHONY`)

**Interfaces:**
- Consumes: `local/accounts.csv` (columns `account_id,api_key` — already produced by `make seed`/`make setup`), `local/sample.pdf` (from Task 1).
- Produces: exit code 0 (all iterations passed) or 1 (at least one failed) from `local/smoke_test.py`; a `run` Makefile target.

- [ ] **Step 1: Write `local/smoke_test.py`**

```python
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
    if host == "minio":
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
```

- [ ] **Step 2: Add the `run` target to `Makefile`**

Change the `.PHONY` line at the top from:

```makefile
.PHONY: setup seed migrate nuke test lint format help
```

to:

```makefile
.PHONY: setup seed migrate nuke run test lint format help
```

Add this target (placed after `seed:`, before `migrate:`, to keep it near the other account/data-dependent commands):

```makefile
run:         ## Smoke test the whole system end-to-end. Usage: make run COUNT=100
	poetry run python local/smoke_test.py $(COUNT)
```

- [ ] **Step 3: Verify a single run passes**

Precondition: the local stack must be running (`docker compose ps` shows everything `Up`) and `local/accounts.csv` must exist (from `make setup`/`make seed`).

Run: `make run COUNT=1`
Expected: one line like `[1] ok (0.3s)`, then `1/1 passed`, and exit code 0 (check with `echo $?` immediately after).

- [ ] **Step 4: Verify a concurrent multi-run passes**

Run: `make run COUNT=20`
Expected: 20 result lines (interleaved order is fine — they run concurrently), then `20/20 passed`, exit code 0.

- [ ] **Step 5: Verify failure reporting works**

Temporarily stop the worker so jobs never complete, confirm the script reports timeouts instead of hanging forever or crashing, then restore the worker:

```bash
docker compose stop worker
make run COUNT=2
# Expected: after ~60s, two lines like "[1] FAILED: timed out after 60s" /
# "[2] FAILED: timed out after 60s", then "0/2 passed", exit code 1.
docker compose start worker
```

- [ ] **Step 6: Commit**

```bash
git add local/smoke_test.py Makefile
git commit -m "feat: add make run smoke test script for end-to-end pipeline checks"
```

---

## Self-Review Notes

- **Spec coverage:** DNS/minio workaround (spec section "The MinIO hostname problem") → Task 2 Step 1's `socket.getaddrinfo` patch. Script behavior (read account, read sample PDF, per-iteration flow, concurrency, reporting, exit code) → Task 2 Step 1. Sample PDF → Task 1. Makefile wiring → Task 2 Step 2. 60s timeout sizing rationale → Global Constraints + inline comment. "No artifact fetch" exclusion → Global Constraints and the script simply stops polling at `completed`/`failed`.
- **Placeholder scan:** no TBDs; every step has literal code or an exact command with expected output.
- **Type consistency:** `_run_one` returns `bool` in both the success and failure paths (Task 2 Step 1); `_main` sums those `bool`s directly (`sum(results)`), consistent with `asyncio.gather` returning a list in submission order.
- **Repo-state check:** verified empirically against the real repo that `git add local/<file>` is blocked by the current `.gitignore` and that per-file negation under an excluded directory doesn't work — added Task 1 Step 0 (`local/` → `local/*` + negations) as the fix, ordered before both files that depend on it are created/committed.
