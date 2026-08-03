"""Smoke test the whole document pipeline end to end, COUNT times."""

import asyncio
import sys
import time
from dataclasses import dataclass, field

from pipeline.client import JobFailed, PipelineClient
from pipeline.fixtures import SAMPLE_PDF

POLL_INTERVAL_SECONDS = 1
BASE_POLL_TIMEOUT_SECONDS = 60


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


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    sys.exit(asyncio.run(_main(count)))
