"""Scenario 1: worker-kill — hard kill mid-job.

Claimed: redelivery plus the idempotency check recovers the job.
Expected: real gap. consumer.py drops any redelivered message whose job is
not QUEUED, a SIGKILL mid-job leaves the job in STARTED, and there is no
lease expiry, heartbeat, or reaper — so the job should be stuck permanently.
"""

from uuid import UUID

from .base import Report, ScenarioContext


async def run(ctx: ScenarioContext) -> Report:
    report = Report(scenario="worker-kill")

    try:
        doc = await ctx.client.submit_document()
        pdf_path = ctx.fixtures.slow_pdf()
        await ctx.client.upload(doc.upload_url, pdf_path.read_bytes())
        report.record("submitted", f"document_id={doc.id}")

        job_id = await ctx.client.start_processing(doc.id)
        report.record("processing_started", f"job_id={job_id}")

        started = ctx.jobs.wait_for_status(job_id, "started", timeout=15)
        report.record("job_started", f"attempts={started.attempts}")

        claimer = _find_claiming_worker(ctx, job_id)
        report.record("claiming_worker_identified", claimer)

        ctx.docker.kill(claimer)
        report.record("worker_killed", claimer)

        history = ctx.jobs.watch(job_id, duration=60)
        for snap in history:
            report.record(
                "status_observed",
                f"status={snap.status} attempts={snap.attempts}",
            )

        final = history[-1] if history else started
        depth = ctx.docker.queue_depth()
        report.record("final_queue_depth", str(depth))

        report.summary = (
            f"final_status={final.status} attempts={final.attempts} "
            f"reached_terminal={final.status in ('completed', 'failed')} "
            f"queue_depth={depth}"
        )
    except Exception as e:
        report.record("scenario_error", str(e))
        report.summary = f"scenario raised before completing: {e}"

    return report


def _find_claiming_worker(ctx: ScenarioContext, job_id: UUID) -> str:
    containers = ctx.docker.worker_containers()
    log_text = ctx.docker.logs("worker", since="2m")
    for line in log_text.splitlines():
        if str(job_id) in line and "job_started" in line:
            short_name = line.split("|", 1)[0].strip()
            for container in containers:
                if container.endswith(short_name):
                    return container
            raise RuntimeError(
                f"job {job_id}'s log line matched short name "
                f"{short_name!r} but no container in {containers} "
                "matches it"
            )
    raise RuntimeError(f"no worker log line found for job {job_id}")
