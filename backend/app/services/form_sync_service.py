from app.database.crud import candidates_db
from app.prompts.screen_prompts import (
    SCREENING_SYSTEM_PROMPT,
    build_screening_user_prompt,
)
from app.schemas.candidates_schema import (
    ApplicationCreate,
    ApplicationScreeningResult,
    CandidateCreate,
    CandidateIdentityLookup,
    FormSyncItem,
    FormSyncItemStatus,
    FormSyncResult,
    ScreeningDecision,
)
from app.schemas.jobs_schema import JobRead
from app.schemas.google_forms_schema import GoogleFormSubmission
from app.services.ai.base import TextAIProvider
from app.services.google_forms import (
    GoogleFormsIntegrationError,
    GoogleFormsService,
)
from app.utils.anonymizer import anonymize_applicant_text


def sync_form_responses(
    job: JobRead,
    *,
    forms_service: GoogleFormsService,
    ai_provider: TextAIProvider,
) -> FormSyncResult:
    if not job.google_form_id:
        raise ValueError("job has no linked Google Form")
    if not job.jd_markdown:
        raise ValueError("job description is required before sync")

    submissions = forms_service.list_application_responses(job.google_form_id)
    items: list[FormSyncItem] = []
    for submission in submissions:
        items.append(
            _sync_submission(
                job,
                submission,
                forms_service=forms_service,
                ai_provider=ai_provider,
            )
        )

    return FormSyncResult(
        total_responses=len(submissions),
        synced=sum(item.status is FormSyncItemStatus.synced for item in items),
        skipped_duplicates=sum(item.status is FormSyncItemStatus.duplicate for item in items),
        errors=sum(item.status is FormSyncItemStatus.error for item in items),
        items=items,
    )


def _sync_submission(
    job: JobRead,
    submission: GoogleFormSubmission,
    *,
    forms_service: GoogleFormsService,
    ai_provider: TextAIProvider,
) -> FormSyncItem:
    existing_response = candidates_db.get_application_for_form_response(
        job.id, submission.response_id
    )
    if existing_response is not None:
        return FormSyncItem(
            response_id=submission.response_id,
            candidate_name=submission.applicant_name,
            email=submission.email,
            application_id=existing_response.id,
            agent_decision=existing_response.agent_decision,
            pipeline_status=existing_response.pipeline_status,
            screening_summary=existing_response.screening_summary,
            status=FormSyncItemStatus.duplicate,
            detail="This form response was already synced.",
        )

    name = (submission.applicant_name or "").strip()
    email = (submission.email or "").strip()
    if not name or not email:
        return _sync_error(submission, "Required name or email is missing from the response.")

    phone = _answer_by_keyword(
        submission.answers, ("phone", "mobile", "contact number")
    )
    linkedin_url = _answer_by_keyword(submission.answers, ("linkedin",))
    try:
        identity = CandidateIdentityLookup(
            email=email,
            phone=phone,
            linkedin_url=linkedin_url,
        )
        candidate = candidates_db.find_candidate_by_identity(identity)
    except Exception:
        return _sync_error(submission, "Applicant identity could not be matched safely.")

    if candidate is not None:
        existing_application = candidates_db.get_application_for_candidate_job(
            candidate.id, job.id
        )
        if existing_application is not None:
            return FormSyncItem(
                response_id=submission.response_id,
                candidate_name=candidate.full_name,
                email=candidate.email,
                application_id=existing_application.id,
                agent_decision=existing_application.agent_decision,
                pipeline_status=existing_application.pipeline_status,
                screening_summary=existing_application.screening_summary,
                status=FormSyncItemStatus.duplicate,
                detail="This candidate already has an application for this job.",
            )

    try:
        resume_text = forms_service.extract_resume_text(submission)
    except GoogleFormsIntegrationError as error:
        return _sync_error(submission, str(error))
    except Exception:
        return _sync_error(
            submission,
            "A readable, text-based PDF résumé is required for screening.",
        )

    anonymized_resume = anonymize_applicant_text(
        resume_text,
        full_name=name,
        email=email,
    )
    raw_form_text = "\n".join(
        f"{question}: {answer}" for question, answer in submission.answers.items()
    )
    anonymized_form_text = anonymize_applicant_text(
        raw_form_text,
        full_name=name,
        email=email,
    )
    try:
        screening = ai_provider.generate_structured(
            system_instruction=SCREENING_SYSTEM_PROMPT,
            user_content=build_screening_user_prompt(
                job_description=job.jd_markdown or "",
                anonymized_resume_text=anonymized_resume,
                anonymized_form_responses=anonymized_form_text,
            ),
            response_model=ApplicationScreeningResult,
        )
        screening = ApplicationScreeningResult.model_validate(screening)
    except Exception:
        return _sync_error(submission, "Screening could not be completed for this response.")

    try:
        if candidate is None:
            candidate = candidates_db.create_candidate(
                CandidateCreate(
                    full_name=name,
                    email=email,
                    phone=phone,
                    linkedin_url=linkedin_url,
                )
            )
        application = candidates_db.create_screened_application(
            ApplicationCreate(candidate_id=candidate.id, job_id=job.id),
            response_id=submission.response_id,
            form_responses=submission.answers,
            screening=screening,
        )
    except Exception:
        return _sync_error(submission, "Application could not be saved; sync can be retried.")

    return FormSyncItem(
        response_id=submission.response_id,
        candidate_name=candidate.full_name,
        email=candidate.email,
        application_id=application.id,
        agent_decision=screening.agent_decision,
        pipeline_status=application.pipeline_status,
        screening_summary=screening.screening_summary,
        status=FormSyncItemStatus.synced,
    )


def _answer_by_keyword(answers: dict[str, str], keywords: tuple[str, ...]) -> str | None:
    for question, answer in answers.items():
        normalized = question.casefold()
        if any(keyword in normalized for keyword in keywords):
            return answer.strip() or None
    return None


def _sync_error(submission: GoogleFormSubmission, detail: str) -> FormSyncItem:
    return FormSyncItem(
        response_id=submission.response_id,
        candidate_name=submission.applicant_name,
        email=submission.email,
        status=FormSyncItemStatus.error,
        detail=detail,
    )