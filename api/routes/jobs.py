from app.api.schemas.requests.jobs import ProcessDocumentRequest
from app.api.schemas.responses.jobs import JobResponse
from app.core.dependencies import CurrentAccount, DBSession, JobServiceDep
from app.core.exceptions import JobNotFoundException
from app.dtos.job import CreateJobDTO, JobDTO
from fastapi import APIRouter

router = APIRouter()


def _to_response(job: JobDTO) -> JobResponse:
    return JobResponse(
        id=job.id,
        document_id=job.document_id,
        status=job.status,
        artifact_types=job.artifact_types,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        error_message=job.error_message,
        created_at=job.created_at,
        queued_at=job.queued_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        last_attempt_at=job.last_attempt_at,
        failed_at=job.failed_at,
    )


@router.post(
    "/documents/{document_id}/process",
    response_model=JobResponse,
    status_code=201,
)
async def process_document(
    document_id: int,
    body: ProcessDocumentRequest,
    account: CurrentAccount,
    session: DBSession,
    job_service: JobServiceDep,
) -> JobResponse:
    dto = CreateJobDTO(
        account_id=account.id,
        document_id=document_id,
        artifact_types=body.artifact_types,
    )
    job = await job_service.create(session, dto)
    return _to_response(job)


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    account: CurrentAccount,
    session: DBSession,
    job_service: JobServiceDep,
) -> JobResponse:
    job = await job_service.get(session, job_id, account.id)
    if job is None:
        raise JobNotFoundException()
    return _to_response(job)
