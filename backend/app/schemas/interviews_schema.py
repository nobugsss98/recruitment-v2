from datetime import date
from enum import Enum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class InterviewStatus(str, Enum):
    pending = "pending"
    complete = "complete"


class InterviewScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheduled_at: AwareDatetime


class InterviewRoundUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    interview_date: date | None = None
    feedback: str | None = Field(default=None, max_length=5000)
    status: InterviewStatus | None = None

    @model_validator(mode="after")
    def require_update_field(self) -> "InterviewRoundUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one interview field must be provided")
        return self


class InterviewRoundRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    application_id: UUID
    sequence_order: int = Field(gt=0)
    scheduled_at: AwareDatetime | None
    interview_date: date | None
    local_audio_path: str | None
    feedback: str | None
    status: InterviewStatus
    created_at: AwareDatetime


class InterviewRecordingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    interview_id: UUID
    sequence_order: int = Field(gt=0)
    interview_date: date
    local_audio_path: str = Field(min_length=1, max_length=1024)
    recording_verified: bool