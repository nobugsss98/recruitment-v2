from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    model_validator,
)

from app.schemas.interviews_schema import InterviewRoundRead


class ApplicationStage(str, Enum):
    sync_evaluation = "sync_evaluation"
    technical_interview = "technical_interview"
    ceo_review = "ceo_review"
    closed = "closed"


class ScreeningDecision(str, Enum):
    passed = "pass"
    failed = "fail"


class PipelineStatus(str, Enum):
    failed_at_sync = "failed_at_sync"
    active_pipeline = "active_pipeline"
    pending_ceo_decision = "pending_ceo_decision"
    closed_complete = "closed_complete"


class FinalDecision(str, Enum):
    pending = "pending"
    passed = "pass"
    failed = "fail"


class CandidateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, min_length=1, max_length=32)
    linkedin_url: HttpUrl | None = None


class CandidateIdentityLookup(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=1, max_length=32)
    linkedin_url: HttpUrl | None = None

    @model_validator(mode="after")
    def require_identity_key(self) -> "CandidateIdentityLookup":
        if not any((self.email, self.phone, self.linkedin_url)):
            raise ValueError("at least one candidate identity key is required")
        return self


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    full_name: str
    email: EmailStr
    phone: str | None
    linkedin_url: HttpUrl | None
    created_at: AwareDatetime


class ApplicationScreeningResult(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    agent_decision: ScreeningDecision
    screening_summary: str = Field(min_length=1, max_length=2000)


class ApplicantSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, min_length=1, max_length=32)
    linkedin_url: HttpUrl | None = None
    age: int | None = Field(default=None, ge=0)
    gender: str | None = Field(default=None, min_length=1, max_length=100)
    resume_text: str = Field(min_length=1, max_length=100000)
    form_responses: dict[str, str] = Field(default_factory=dict, max_length=100)


class HROverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    hr_username: str = Field(min_length=1, max_length=150)


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    candidate_id: UUID
    job_id: UUID
    current_stage: ApplicationStage
    agent_decision: ScreeningDecision | None
    screening_summary: str | None
    hr_override_status: ScreeningDecision | None
    examiner: str
    pipeline_status: PipelineStatus
    final_decision: FinalDecision
    remarks: str | None
    created_at: AwareDatetime
    google_form_response_id: str | None = None
    form_responses: dict[str, str] = Field(default_factory=dict)


class ApplicationApplicantRead(ApplicationRead):
    candidate_name: str
    email: EmailStr
    phone: str | None = None


class FormSyncItemStatus(str, Enum):
    synced = "synced"
    duplicate = "duplicate"
    error = "error"


class FormSyncItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_id: str
    candidate_name: str | None = None
    email: EmailStr | None = None
    application_id: UUID | None = None
    agent_decision: ScreeningDecision | None = None
    pipeline_status: PipelineStatus | None = None
    screening_summary: str | None = None
    status: FormSyncItemStatus
    detail: str | None = None


class FormSyncResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_responses: int = Field(ge=0)
    synced: int = Field(ge=0)
    skipped_duplicates: int = Field(ge=0)
    errors: int = Field(ge=0)
    items: list[FormSyncItem]


class CandidateHistoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_id: UUID
    job_id: UUID
    job_title: str
    current_stage: ApplicationStage
    pipeline_status: PipelineStatus
    final_decision: FinalDecision
    remarks: str | None
    screening_summary: str | None = None
    created_at: AwareDatetime


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: UUID
    job_id: UUID


class ApplicationDashboardRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    application_id: UUID
    candidate_id: UUID
    job_id: UUID
    full_name: str
    email: EmailStr
    phone: str | None
    linkedin_url: HttpUrl | None
    job_title: str
    current_stage: ApplicationStage
    agent_decision: ScreeningDecision | None
    screening_summary: str | None
    hr_override_status: ScreeningDecision | None
    examiner: str
    pipeline_status: PipelineStatus
    final_decision: FinalDecision
    remarks: str | None
    application_created_at: AwareDatetime


class FinalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    final_decision: FinalDecision
    remarks: str | None = Field(default=None, max_length=5000)


class ApplicationDossier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application: ApplicationRead
    interviews: list[InterviewRoundRead]