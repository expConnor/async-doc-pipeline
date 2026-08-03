"""Smoke test the whole document pipeline end to end, COUNT times."""

import asyncio
import sys
import time
from dataclasses import dataclass, field

from pipeline.client import JobFailed, PipelineClient
from pipeline.fixtures import SAMPLE_PDF

POLL_INTERVAL_SECONDS = 1
BASE_POLL_TIMEOUT_SECONDS = 60


# `field(default=None, compare=False)` does two things to the `error`
# attribute: `default=None` gives it a default value (dataclass fields with
# defaults must come after fields without one, which is why `error` is
# listed last), and `compare=False` excludes it from the `==` comparison
# @dataclass auto-generates — so two Results with the same index/ok/elapsed
# but different error text would still count as equal. Nothing in this file
# actually compares two Results, so this is mostly documenting intent: the
# error message is metadata, not part of what makes two results "the same".
@dataclass
class Result:
    index: int
    ok: bool
    elapsed: float
    error: str | None = field(default=None, compare=False)


async def _run_one(
    client: PipelineClient, index: int, pdf_bytes: bytes, poll_timeout: float
) -> Result:
    start = time.monotonic()
    try:
        doc = await client.submit_document()
        await client.upload(doc.upload_url, pdf_bytes)
        job_id = await client.start_processing(doc.id)
        await client.wait_for_completion(
            job_id, timeout=poll_timeout, poll_interval=POLL_INTERVAL_SECONDS
        )
        return Result(index, True, time.monotonic() - start)
    except JobFailed as e:
        return Result(
            index,
            False,
            time.monotonic() - start,
            error=f"job failed: {e.job.get('error_message')}",
        )
    except (TimeoutError, Exception) as e:
        return Result(index, False, time.monotonic() - start, error=str(e))


def _format_result(r: Result) -> str:
    if r.ok:
        return f"[{r.index}] ok ({r.elapsed:.1f}s)"
    return f"[{r.index}] FAILED: {r.error}"


async def _main(count: int) -> int:
    start = time.monotonic()
    poll_timeout = BASE_POLL_TIMEOUT_SECONDS + count
    pdf_bytes = SAMPLE_PDF.read_bytes()

    async with PipelineClient() as client:
        # `_run_one(...) for i in range(1, count + 1)` is a generator
        # expression — it lazily produces one `_run_one(...)` coroutine per
        # document, without calling any of them yet. The `*` unpacks that
        # sequence into separate positional arguments to `asyncio.gather`,
        # which is what actually starts them all running concurrently and
        # waits for every one to finish before returning their results in the
        # same order. This is why `make run COUNT=12` submits 12 documents at
        # once instead of one after another — asyncio.gather is what makes it
        # concurrent, not just a loop calling _run_one 12 times.
        results = await asyncio.gather(
            *(
                _run_one(client, i, pdf_bytes, poll_timeout)
                for i in range(1, count + 1)
            )
        )

    for r in results:
        print(_format_result(r))

    passed = sum(1 for r in results if r.ok)
    total_elapsed = time.monotonic() - start
    print(f"{passed}/{count} passed ({total_elapsed:.1f}s total)")
    return 0 if passed == count else 1


# `if __name__ == "__main__":` only runs when this file is executed directly
# (`python smoke.py`), not when it's imported by something else — the
# standard way a Python script marks "this is my entry point". `sys.argv` is
# the list of command-line arguments; `sys.argv[0]` is always the script name
# itself, so `sys.argv[1]` is the first argument after it (COUNT, from
# `make run COUNT=12`). `asyncio.run(...)` is the bridge from regular
# (synchronous) code into async code — every `await` in this file only works
# inside something `asyncio.run` (or an equivalent) is driving; it's the one
# call that actually starts the async event loop. `sys.exit(...)` passes
# `_main`'s return value (0 or 1) out as the process's exit code, which is
# how the Makefile's `run` target can tell success from failure.
if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    sys.exit(asyncio.run(_main(count)))
