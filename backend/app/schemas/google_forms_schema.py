from enum import Enum

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


class GoogleFormQuestionType(str, Enum):
    short_text = "short_text"
    paragraph = "paragraph"
    multiple_choice = "multiple_choice"
    checkbox = "checkbox"


class GoogleFormQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=300)
    question_type: GoogleFormQuestionType
    options: list[str] = Field(default_factory=list, max_length=12)
    required: bool = True

    @field_validator("options")
    @classmethod
    def validate_options(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("choice options must not be empty")
        if len({value.casefold() for value in normalized}) != len(normalized):
            raise ValueError("choice options must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_question_type_options(self) -> "GoogleFormQuestion":
        is_choice = self.question_type in {
            GoogleFormQuestionType.multiple_choice,
            GoogleFormQuestionType.checkbox,
        }
        if is_choice and len(self.options) < 2:
            raise ValueError("choice questions require at least two unique options")
        if not is_choice and self.options:
            raise ValueError("text questions cannot include choice options")
        return self


class GoogleFormQuestionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[GoogleFormQuestion] = Field(min_length=2, max_length=8)


class GoogleFormCloneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    template_file_id: str | None = Field(default=None, min_length=1, max_length=255)
    destination_folder_id: str | None = Field(default=None, min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=200)
    questions: list[GoogleFormQuestion] = Field(min_length=1, max_length=20)


class GoogleFormCloneResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    form_id: str = Field(min_length=1)
    responder_url: AnyHttpUrl
    editor_url: AnyHttpUrl
    questions_added: int = Field(ge=1)


class GoogleFormUploadedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    mime_type: str | None = None


class GoogleFormSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_id: str = Field(min_length=1)
    applicant_name: str | None = None
    email: str | None = None
    answers: dict[str, str]
    resume_files: list[GoogleFormUploadedFile]
    submitted_at: str | None = None