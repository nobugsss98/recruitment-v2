from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_any_role, require_hr
from app.database.crud import jobs_db
from app.database.crud import candidates_db
from app.schemas.auth_schema import UserRead
from app.prompts.jd_prompts import (
    JOB_DESCRIPTION_SYSTEM_PROMPT,
    LINKEDIN_BLURB_SYSTEM_PROMPT,
    build_job_description_user_prompt,
    build_linkedin_blurb_user_prompt,
)
from app.schemas.jobs_schema import JobCreate, JobPatch, JobRead, JobStatus
from app.schemas.google_forms_schema import (
    GoogleFormCloneRequest,
    GoogleFormCloneResult,
    GoogleFormQuestionSet,
)
from app.prompts.form_prompts import FORM_QUESTION_SYSTEM_PROMPT, build_form_questions_user_prompt
from app.schemas.candidates_schema import (
    ApplicationApplicantRead,
    FormSyncResult,
    PipelineStatus,
)
from app.services import audit
from app.services.ai.gemini_flash import GeminiFlashProvider
from app.services.google_forms import (
    GoogleFormsConfigurationError,
    GoogleFormsIntegrationError,
    GoogleFormsService,
)
from app.services.form_sync_service import sync_form_responses
from app.utils.logging import get_logger

router = APIRouter(prefix="/jobs", tags=["jobs"])
_logger = get_logger("app.jobs")


class JobsStore:
    def create_job(self, job: JobCreate) -> JobRead:
        return jobs_db.create_job(job)

    def list_jobs(self, *, status: JobStatus | None = None) -> list[JobRead]:
        return jobs_db.list_jobs(status=status)

    def get_job(self, job_id: UUID) -> JobRead | None:
        return jobs_db.get_job(job_id)

    def update_job(self, job_id: UUID, patch: JobPatch) -> JobRead | None:
        return jobs_db.update_job(job_id, patch)


_jobs_store = JobsStore()


def get_jobs_store() -> JobsStore:
    return _jobs_store


def get_ai_provider() -> GeminiFlashProvider:
    return GeminiFlashProvider()


@router.get("", response_model=list[JobRead], dependencies=[Depends(require_any_role)])
def list_jobs_route(*, status: JobStatus | None = None) -> list[JobRead]:
    return get_jobs_store().list_jobs(status=status)


@router.post(
    "",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_hr)],
)
def create_job_route(
    job: JobCreate,
    current_user: UserRead = Depends(get_current_user),
) -> JobRead:
    created = get_jobs_store().create_job(job)
    audit.record_audit(
        action="job_created",
        entity="job",
        entity_id=created.id,
        actor=current_user,
        metadata={"title": created.title},
    )
    return created


@router.get("/{job_id}", response_model=JobRead, dependencies=[Depends(require_any_role)])
def get_job_route(job_id: UUID) -> JobRead:
    row = get_jobs_store().get_job(job_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return row


@router.patch("/{job_id}", response_model=JobRead, dependencies=[Depends(require_hr)])
def patch_job_route(job_id: UUID, patch: JobPatch) -> JobRead:
    row = get_jobs_store().update_job(job_id, patch)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return row


@router.post("/{job_id}/generate-jd", response_model=JobRead, dependencies=[Depends(require_hr)])
def generate_jd_route(job_id: UUID) -> JobRead:
    row = get_jobs_store().get_job(job_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    payload = JobCreate(
        title=row.title,
        tech_stack=row.tech_stack,
        seniority=row.seniority,
        compensation_min=row.compensation_min,
        compensation_max=row.compensation_max,
    )
    provider = get_ai_provider()
    markdown = provider.generate_text(
        system_instruction=JOB_DESCRIPTION_SYSTEM_PROMPT,
        user_content=build_job_description_user_prompt(payload),
    )

    updated = get_jobs_store().update_job(job_id, JobPatch(jd_markdown=markdown))
    if updated is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="job update failed")
    return updated


@router.post(
    "/{job_id}/generate-form-questions",
    response_model=GoogleFormQuestionSet,
    dependencies=[Depends(require_hr)],
)
def generate_form_questions_route(job_id: UUID) -> GoogleFormQuestionSet:
    row = get_jobs_store().get_job(job_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    payload = JobCreate(
        title=row.title,
        tech_stack=row.tech_stack,
        seniority=row.seniority,
        compensation_min=row.compensation_min,
        compensation_max=row.compensation_max,
    )
    result = get_ai_provider().generate_structured(
        system_instruction=FORM_QUESTION_SYSTEM_PROMPT,
        user_content=build_form_questions_user_prompt(payload),
        response_model=GoogleFormQuestionSet,
    )
    return GoogleFormQuestionSet.model_validate(result)


@router.post("/{job_id}/clone-form", response_model=GoogleFormCloneResult, dependencies=[Depends(require_hr)])
def clone_form_route(job_id: UUID, question_set: GoogleFormQuestionSet) -> GoogleFormCloneResult:
    row = get_jobs_store().get_job(job_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    payload = JobCreate(
        title=row.title,
        tech_stack=row.tech_stack,
        seniority=row.seniority,
        compensation_min=row.compensation_min,
        compensation_max=row.compensation_max,
    )
    service = GoogleFormsService()
    try:
        result = service.clone_application_form(
            GoogleFormCloneRequest(
                title=f"{payload.title} Application",
                questions=question_set.questions,
            )
        )
    except GoogleFormsIntegrationError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except GoogleFormsConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    updated = get_jobs_store().update_job(
        job_id,
        JobPatch(google_form_id=result.form_id, google_form_url=str(result.responder_url)),
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="job update failed")
    return result


@router.post("/{job_id}/linkedin-blurb", response_model=JobRead, dependencies=[Depends(require_hr)])
def linkedin_blurb_route(job_id: UUID) -> JobRead:
    row = get_jobs_store().get_job(job_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    if not row.jd_markdown:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="job description must be generated or saved before creating a post",
        )
    if not row.google_form_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="application form must be cloned before creating a post",
        )

    payload = JobCreate(
        title=row.title,
        tech_stack=row.tech_stack,
        seniority=row.seniority,
        compensation_min=row.compensation_min,
        compensation_max=row.compensation_max,
    )
    blurb = get_ai_provider().generate_text(
        system_instruction=LINKEDIN_BLURB_SYSTEM_PROMPT,
        user_content=build_linkedin_blurb_user_prompt(
            payload,
            jd_markdown=row.jd_markdown,
            form_url=row.google_form_url,
        ),
    )
    updated = get_jobs_store().update_job(job_id, JobPatch(linkedin_blurb=blurb))
    if updated is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="job update failed")
    return updated


@router.get(
    "/{job_id}/applications",
    response_model=list[ApplicationApplicantRead],
    dependencies=[Depends(require_any_role)],
)
def list_job_applications_route(
    job_id: UUID,
    *,
    pipeline_status: PipelineStatus | None = None,
) -> list[ApplicationApplicantRead]:
    if get_jobs_store().get_job(job_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return candidates_db.list_job_applications(job_id, pipeline_status=pipeline_status)


@router.post("/{job_id}/sync", response_model=FormSyncResult, dependencies=[Depends(require_hr)])
def sync_applicants_route(
    job_id: UUID,
    current_user: UserRead = Depends(get_current_user),
) -> FormSyncResult:
    row = get_jobs_store().get_job(job_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    if not row.jd_markdown:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="job description is required before sync")
    if not row.google_form_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="application form is required before sync")
    _logger.info("sync started", job_id=str(job_id))
    try:
        result = sync_form_responses(
            row,
            forms_service=GoogleFormsService(),
            ai_provider=get_ai_provider(),
        )
    except GoogleFormsConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except GoogleFormsIntegrationError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    _logger.info(
        "sync finished",
        job_id=str(job_id),
        total_responses=result.total_responses,
        synced=result.synced,
        skipped_duplicates=result.skipped_duplicates,
        errors=result.errors,
    )
    audit.record_audit(
        action="sync_run",
        entity="job",
        entity_id=job_id,
        actor=current_user,
        metadata={
            "total_responses": result.total_responses,
            "synced": result.synced,
            "skipped_duplicates": result.skipped_duplicates,
            "errors": result.errors,
        },
    )
    return result
