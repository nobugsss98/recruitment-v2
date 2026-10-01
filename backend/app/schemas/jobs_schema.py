from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class JobStatus(str, Enum):
    draft = "draft"
    posted = "posted"
    closed = "closed"


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    tech_stack: str = Field(min_length=1, max_length=2000)
    seniority: str = Field(min_length=1, max_length=100)
    compensation_min: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    compensation_max: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )

    @model_validator(mode="after")
    def validate_compensation_range(self) -> "JobCreate":
        if (
            self.compensation_min is not None
            and self.compensation_max is not None
            and self.compensation_min > self.compensation_max
        ):
            raise ValueError("compensation_min must not exceed compensation_max")
        return self


class JobPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=200)
    tech_stack: str | None = Field(default=None, min_length=1, max_length=2000)
    seniority: str | None = Field(default=None, min_length=1, max_length=100)
    compensation_min: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    compensation_max: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    jd_markdown: str | None = None
    google_form_id: str | None = Field(default=None, min_length=1, max_length=255)
    google_form_url: str | None = Field(default=None, min_length=1, max_length=2048)
    linkedin_blurb: str | None = None
    status: JobStatus | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> "JobPatch":
        if not self.model_fields_set:
            raise ValueError("at least one job field must be provided")
        if (
            self.compensation_min is not None
            and self.compensation_max is not None
            and self.compensation_min > self.compensation_max
        ):
            raise ValueError("compensation_min must not exceed compensation_max")
        return self


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    title: str
    tech_stack: str
    seniority: str
    compensation_min: Decimal | None
    compensation_max: Decimal | None
    jd_markdown: str | None
    google_form_id: str | None
    google_form_url: str | None
    linkedin_blurb: str | None
    status: JobStatus
    created_at: AwareDatetime