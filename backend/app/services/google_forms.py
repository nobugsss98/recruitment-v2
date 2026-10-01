from pathlib import Path
from typing import Any, Callable
from io import BytesIO
import logging

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials as OAuthCredentials
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from pypdf import PdfReader

from app.config import Settings, settings
from app.prompts.form_prompts import (
    FORM_QUESTION_SYSTEM_PROMPT,
    build_form_questions_user_prompt,
)
from app.schemas.google_forms_schema import (
    GoogleFormCloneRequest,
    GoogleFormCloneResult,
    GoogleFormQuestion,
    GoogleFormQuestionSet,
    GoogleFormQuestionType,
    GoogleFormSubmission,
    GoogleFormUploadedFile,
)
from app.schemas.jobs_schema import JobCreate


class GoogleFormsConfigurationError(RuntimeError):
    """Raised when Google Forms settings or credentials are unavailable."""


class GoogleFormsIntegrationError(RuntimeError):
    """Raised when a Drive or Forms API operation fails."""


_GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/forms.body",
)
_GOOGLE_RESPONSES_SCOPE = "https://www.googleapis.com/auth/forms.responses.readonly"
_LOGGER = logging.getLogger(__name__)


class GoogleFormsService:
    def __init__(
        self,
        *,
        settings_provider: Callable[[], Settings] = lambda: settings,
        drive_service: Any | None = None,
        forms_service: Any | None = None,
        service_builder: Callable[..., Any] = build,
        credentials_factory: Callable[..., Any] = Credentials.from_service_account_file,
        oauth_flow_factory: Callable[..., Any] = InstalledAppFlow.from_client_secrets_file,
    ) -> None:
        self._settings_provider = settings_provider
        self._drive_service = drive_service
        self._forms_service = forms_service
        self._service_builder = service_builder
        self._credentials_factory = credentials_factory
        self._oauth_flow_factory = oauth_flow_factory

    def generate_and_clone_application_form(
        self,
        job: JobCreate,
        ai_provider: Any,
    ) -> GoogleFormCloneResult:
        generated = ai_provider.generate_structured(
            system_instruction=FORM_QUESTION_SYSTEM_PROMPT,
            user_content=build_form_questions_user_prompt(job),
            response_model=GoogleFormQuestionSet,
        )
        question_set = GoogleFormQuestionSet.model_validate(generated)
        return self.clone_application_form(
            GoogleFormCloneRequest(
                title=f"{job.title} Application",
                questions=question_set.questions,
            )
        )

    def clone_application_form(
        self,
        request: GoogleFormCloneRequest,
    ) -> GoogleFormCloneResult:
        configuration = self._settings_provider()
        template_id = request.template_file_id or configuration.google_form_template_id
        folder_id = request.destination_folder_id or configuration.google_drive_folder_id
        if not template_id:
            raise GoogleFormsConfigurationError("GOOGLE_FORM_TEMPLATE_ID is required")

        drive_service, forms_service = self._get_services(
            configuration,
            scopes=(*_GOOGLE_SCOPES, _GOOGLE_RESPONSES_SCOPE),
        )
        copied_file_id: str | None = None
        try:
            copied_file = (
                drive_service.files()
                .copy(
                    fileId=template_id,
                    body={
                        "name": request.title,
                        **({"parents": [folder_id]} if folder_id else {}),
                    },
                    supportsAllDrives=True,
                )
                .execute()
            )
            copied_file_id = copied_file.get("id") if isinstance(copied_file, dict) else None
            if not isinstance(copied_file_id, str) or not copied_file_id.strip():
                raise GoogleFormsIntegrationError("Drive did not return the copied form ID")

            existing_form = (
                forms_service.forms().get(formId=copied_file_id).execute()
            )
            existing_items = existing_form.get("items", [])
            if not isinstance(existing_items, list):
                raise GoogleFormsIntegrationError("Copied form returned invalid items")

            batch_requests: list[dict[str, object]] = [
                {
                    "updateFormInfo": {
                        "info": {"title": request.title},
                        "updateMask": "title",
                    }
                }
            ]
            first_new_index = len(existing_items)
            questions = self._with_identity_questions(request.questions, existing_items)
            for offset, question in enumerate(questions):
                batch_requests.append(
                    {
                        "createItem": {
                            "item": self._question_item(question),
                            "location": {"index": first_new_index + offset},
                        }
                    }
                )

            (
                forms_service.forms()
                .batchUpdate(
                    formId=copied_file_id,
                    body={"requests": batch_requests},
                )
                .execute()
            )
            updated_form = forms_service.forms().get(formId=copied_file_id).execute()
            responder_url = updated_form.get("responderUri")
            if not isinstance(responder_url, str) or not responder_url.strip():
                raise GoogleFormsIntegrationError("Forms API did not return a responder URL")

            return GoogleFormCloneResult(
                form_id=copied_file_id,
                responder_url=responder_url,
                editor_url=f"https://docs.google.com/forms/d/{copied_file_id}/edit",
                questions_added=len(questions),
            )
        except GoogleFormsIntegrationError:
            self._delete_partial_copy(drive_service, copied_file_id)
            raise
        except Exception as error:
            response = getattr(error, "resp", None)
            provider_status = getattr(response, "status", None)
            provider_reason = getattr(error, "reason", None)
            _LOGGER.error(
                "Google Form clone failed during provider operation: type=%s status=%s reason=%s",
                type(error).__name__,
                provider_status,
                provider_reason,
            )
            self._delete_partial_copy(drive_service, copied_file_id)
            if (
                provider_status == 403
                and isinstance(provider_reason, str)
                and "storage quota" in provider_reason.lower()
            ):
                raise GoogleFormsIntegrationError(
                    "The service account has no available My Drive storage quota. "
                    "Set GOOGLE_DRIVE_FOLDER_ID to a folder inside a Shared Drive "
                    "where the service account has Content manager access, or use "
                    "Workspace domain-wide delegation."
                ) from None
            raise GoogleFormsIntegrationError(
                f"Google Drive or Forms API operation failed ({type(error).__name__})"
            ) from None

    def list_application_responses(self, form_id: str) -> list[GoogleFormSubmission]:
        if not isinstance(form_id, str) or not form_id.strip():
            raise ValueError("form_id must be a non-empty string")
        configuration = self._settings_provider()
        drive_service, forms_service = self._get_services(configuration)
        del drive_service
        try:
            form = forms_service.forms().get(formId=form_id).execute()
            question_titles = self._question_titles(form)
            submissions: list[GoogleFormSubmission] = []
            page_token: str | None = None
            while True:
                request: dict[str, object] = {"formId": form_id, "pageSize": 500}
                if page_token:
                    request["pageToken"] = page_token
                page = forms_service.forms().responses().list(**request).execute()
                responses = page.get("responses", [])
                if not isinstance(responses, list):
                    raise GoogleFormsIntegrationError("Forms API returned invalid responses")
                submissions.extend(
                    self._parse_submission(response, question_titles)
                    for response in responses
                    if isinstance(response, dict)
                )
                page_token = page.get("nextPageToken")
                if not isinstance(page_token, str) or not page_token:
                    break
            return submissions
        except GoogleFormsIntegrationError:
            raise
        except Exception as error:
            raise GoogleFormsIntegrationError(
                f"Google Forms response retrieval failed ({type(error).__name__})"
            ) from None

    def extract_resume_text(self, submission: GoogleFormSubmission) -> str:
        pdf_files = [
            item for item in submission.resume_files
            if item.file_name.casefold().endswith(".pdf")
            or (item.mime_type or "").casefold() == "application/pdf"
        ]
        if not pdf_files:
            raise GoogleFormsIntegrationError("Applicant has no uploaded PDF resume")
        configuration = self._settings_provider()
        drive_service, _ = self._get_services(configuration)
        text_parts: list[str] = []
        try:
            for uploaded_file in pdf_files:
                output = BytesIO()
                downloader = MediaIoBaseDownload(
                    output,
                    drive_service.files().get_media(fileId=uploaded_file.file_id),
                )
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                content = output.getvalue()
                reader = PdfReader(BytesIO(content))
                text_parts.extend(
                    page_text.strip()
                    for page in reader.pages
                    if (page_text := page.extract_text() or "").strip()
                )
        except Exception as error:
            raise GoogleFormsIntegrationError(
                f"Uploaded PDF could not be read ({type(error).__name__})"
            ) from None
        extracted_text = "\n".join(text_parts).strip()
        if not extracted_text:
            raise GoogleFormsIntegrationError("Uploaded PDF contains no extractable text")
        return extracted_text

    @staticmethod
    def _question_titles(form: object) -> dict[str, str]:
        if not isinstance(form, dict) or not isinstance(form.get("items", []), list):
            raise GoogleFormsIntegrationError("Forms API returned invalid form items")
        titles: dict[str, str] = {}
        for item in form.get("items", []):
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            question_item = item.get("questionItem")
            question = question_item.get("question") if isinstance(question_item, dict) else None
            question_id = question.get("questionId") if isinstance(question, dict) else None
            if isinstance(title, str) and isinstance(question_id, str):
                titles[question_id] = title
        return titles

    @classmethod
    def _parse_submission(
        cls,
        response: dict[str, Any],
        question_titles: dict[str, str],
    ) -> GoogleFormSubmission:
        response_id = response.get("responseId")
        if not isinstance(response_id, str) or not response_id.strip():
            raise GoogleFormsIntegrationError("Forms API returned a response without an ID")

        answers: dict[str, str] = {}
        resume_files: list[GoogleFormUploadedFile] = []
        raw_answers = response.get("answers", {})
        if not isinstance(raw_answers, dict):
            raise GoogleFormsIntegrationError("Forms API returned invalid answer data")
        for question_id, answer in raw_answers.items():
            if not isinstance(answer, dict):
                continue
            title = question_titles.get(question_id, f"Question {question_id}")
            text_answers = answer.get("textAnswers", {}).get("answers", [])
            if isinstance(text_answers, list):
                values = [
                    item["value"].strip()
                    for item in text_answers
                    if isinstance(item, dict)
                    and isinstance(item.get("value"), str)
                    and item["value"].strip()
                ]
                if values:
                    answers[title] = "; ".join(values)

            upload_answers = answer.get("fileUploadAnswers", {}).get("answers", [])
            if isinstance(upload_answers, list):
                question_uploads: list[GoogleFormUploadedFile] = []
                for uploaded in upload_answers:
                    if not isinstance(uploaded, dict):
                        continue
                    file_id = uploaded.get("fileId")
                    file_name = uploaded.get("fileName")
                    if isinstance(file_id, str) and isinstance(file_name, str):
                        mime_type = uploaded.get("mimeType")
                        file_record = GoogleFormUploadedFile(
                            file_id=file_id,
                            file_name=file_name,
                            mime_type=mime_type if isinstance(mime_type, str) else None,
                        )
                        resume_files.append(file_record)
                        question_uploads.append(file_record)
                if question_uploads:
                    answers[title] = "; ".join(item.file_name for item in question_uploads)

        applicant_name = cls._find_answer(answers, {"name", "full name", "candidate name", "applicant name"})
        if applicant_name is None:
            first_name = cls._find_answer(answers, {"first name", "given name"})
            last_name = cls._find_answer(answers, {"last name", "family name", "surname"})
            if first_name and last_name:
                applicant_name = f"{first_name} {last_name}"

        respondent_email = response.get("respondentEmail")
        email = respondent_email.strip() if isinstance(respondent_email, str) and respondent_email.strip() else cls._find_answer_by_keyword(answers, "email")
        submitted_at = response.get("lastSubmittedTime")
        return GoogleFormSubmission(
            response_id=response_id,
            applicant_name=applicant_name,
            email=email,
            answers=answers,
            resume_files=resume_files,
            submitted_at=submitted_at if isinstance(submitted_at, str) else None,
        )

    @staticmethod
    def _find_answer(answers: dict[str, str], accepted_titles: set[str]) -> str | None:
        for title, value in answers.items():
            normalized = " ".join(title.casefold().split()).rstrip(":")
            if normalized in accepted_titles or GoogleFormsService._is_applicant_name_title(normalized):
                return value
        return None

    @staticmethod
    def _find_answer_by_keyword(answers: dict[str, str], keyword: str) -> str | None:
        for title, value in answers.items():
            if keyword in title.casefold() and "resume" not in title.casefold():
                return value
        return None

    def _get_services(
        self,
        configuration: Settings,
        *,
        scopes: tuple[str, ...] = _GOOGLE_SCOPES,
    ) -> tuple[Any, Any]:
        if self._drive_service is not None and self._forms_service is not None:
            return self._drive_service, self._forms_service

        try:
            if configuration.google_oauth_client_file is not None:
                credentials = self._load_oauth_credentials(configuration, scopes=scopes)
            else:
                credential_file = configuration.google_service_account_file
                if credential_file is None or not credential_file.is_file():
                    raise GoogleFormsConfigurationError(
                        "Set GOOGLE_OAUTH_CLIENT_FILE or provide a readable "
                        "GOOGLE_SERVICE_ACCOUNT_FILE"
                    )
                credentials = self._credentials_factory(
                    str(credential_file), scopes=list(scopes)
                )
            if self._drive_service is None:
                self._drive_service = self._service_builder(
                    "drive", "v3", credentials=credentials, cache_discovery=False
                )
            if self._forms_service is None:
                self._forms_service = self._service_builder(
                    "forms", "v1", credentials=credentials, cache_discovery=False
                )
        except GoogleFormsConfigurationError:
            raise
        except Exception:
            raise GoogleFormsConfigurationError(
                "Google client initialization failed"
            ) from None
        return self._drive_service, self._forms_service

    def _load_oauth_credentials(
        self,
        configuration: Settings,
        *,
        scopes: tuple[str, ...] = _GOOGLE_SCOPES,
    ) -> OAuthCredentials:
        client_file = configuration.google_oauth_client_file
        token_file = configuration.google_oauth_token_file
        if client_file is None or not client_file.is_file():
            raise GoogleFormsConfigurationError(
                "GOOGLE_OAUTH_CLIENT_FILE must point to a readable OAuth client JSON file"
            )
        if token_file is None:
            raise GoogleFormsConfigurationError(
                "GOOGLE_OAUTH_TOKEN_FILE is required when OAuth is enabled"
            )

        credentials: OAuthCredentials | None = None
        if token_file.is_file():
            try:
                credentials = OAuthCredentials.from_authorized_user_file(
                    str(token_file)
                )
            except (ValueError, OSError):
                credentials = None

        has_required_scopes = (
            credentials is not None
            and set(scopes).issubset(set(credentials.scopes or []))
        )
        if credentials is not None and credentials.valid and has_required_scopes:
            return credentials
        needs_consent = not has_required_scopes
        if (
            credentials is not None
            and credentials.expired
            and credentials.refresh_token
            and has_required_scopes
        ):
            try:
                credentials.refresh(Request())
                needs_consent = not credentials.valid
            except Exception:
                needs_consent = True
        else:
            needs_consent = True

        if needs_consent:
            flow = self._oauth_flow_factory(str(client_file), scopes=list(scopes))
            credentials = flow.run_local_server(
                port=0,
                access_type="offline",
                prompt="consent",
            )

        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(credentials.to_json(), encoding="utf-8")
        return credentials

    @staticmethod
    def _question_item(question: GoogleFormQuestion) -> dict[str, object]:
        question_body: dict[str, object] = {"required": question.required}
        if question.question_type in {
            GoogleFormQuestionType.short_text,
            GoogleFormQuestionType.paragraph,
        }:
            question_body["textQuestion"] = {
                "paragraph": question.question_type is GoogleFormQuestionType.paragraph
            }
        else:
            choice_type = (
                "RADIO"
                if question.question_type is GoogleFormQuestionType.multiple_choice
                else "CHECKBOX"
            )
            question_body["choiceQuestion"] = {
                "type": choice_type,
                "options": [{"value": option} for option in question.options],
                "shuffle": False,
            }
        return {
            "title": question.title,
            "questionItem": {"question": question_body},
        }

    @staticmethod
    def _with_identity_questions(
        questions: list[GoogleFormQuestion],
        existing_items: list[dict[str, Any]],
    ) -> list[GoogleFormQuestion]:
        existing_titles = {
            " ".join(str(item.get("title", "")).casefold().split()).rstrip(":")
            for item in existing_items
            if isinstance(item, dict)
        }
        requested_titles = {
            " ".join(question.title.casefold().split()).rstrip(":")
            for question in questions
        }
        result = list(questions)
        if not any(
            GoogleFormsService._is_applicant_name_title(title)
            for title in existing_titles | requested_titles
        ):
            result.insert(
                0,
                GoogleFormQuestion(
                    title="Full name",
                    question_type=GoogleFormQuestionType.short_text,
                    required=True,
                ),
            )
        if not any("email" in title for title in existing_titles | requested_titles):
            result.insert(
                1 if result and "name" in result[0].title.casefold() else 0,
                GoogleFormQuestion(
                    title="Email address",
                    question_type=GoogleFormQuestionType.short_text,
                    required=True,
                ),
            )
        return result

    @staticmethod
    def _is_applicant_name_title(title: str) -> bool:
        normalized = " ".join(title.casefold().split()).rstrip("?:")
        return normalized in {"name", "full name", "candidate name", "applicant name"} or any(
            phrase in normalized
            for phrase in ("full name", "candidate name", "applicant name", "your name")
        )

    @staticmethod
    def _delete_partial_copy(drive_service: Any, copied_file_id: str | None) -> None:
        if copied_file_id is None:
            return
        try:
            drive_service.files().delete(
                fileId=copied_file_id,
                supportsAllDrives=True,
            ).execute()
        except Exception:
            pass