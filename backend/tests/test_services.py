from datetime import date
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from app.config import Settings
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
from app.schemas.candidates_schema import (
    ApplicationScreeningResult,
    FormSyncItemStatus,
    PipelineStatus,
    ScreeningDecision,
)
from app.schemas.jobs_schema import JobCreate
from app.services.form_sync_service import sync_form_responses
from app.services.google_forms import (
    GoogleFormsConfigurationError,
    GoogleFormsIntegrationError,
    GoogleFormsService,
)
from app.services.local_media_service import store_interview_recording


class FakeRequest:
    def __init__(self, response: object = None, error: Exception | None = None):
        self.response = response
        self.error = error

    def execute(self) -> object:
        if self.error is not None:
            raise self.error
        return self.response


class FakeDriveFiles:
    def __init__(self, copied_file: dict[str, object], error: Exception | None = None):
        self.copied_file = copied_file
        self.error = error
        self.copy_calls: list[dict[str, object]] = []
        self.download_calls: list[dict[str, object]] = []
        self.deleted_ids: list[str] = []

    def copy(self, **kwargs: object) -> FakeRequest:
        self.copy_calls.append(kwargs)
        return FakeRequest(self.copied_file, self.error)

    def delete(self, *, fileId: str, **kwargs: object) -> FakeRequest:
        self.deleted_ids.append(fileId)
        return FakeRequest({})

    def get(self, **kwargs: object) -> FakeRequest:
        self.download_calls.append(kwargs)
        return FakeRequest(b"fake-pdf-bytes")

    def get_media(self, **kwargs: object) -> FakeRequest:
        self.download_calls.append(kwargs)
        return FakeRequest(b"fake-pdf-bytes")


class FakeDriveService:
    def __init__(self, files: FakeDriveFiles):
        self._files = files

    def files(self) -> FakeDriveFiles:
        return self._files


class FakeMediaIoBaseDownload:
    def __init__(self, output: BytesIO, request: FakeRequest):
        self.output = output
        self.request = request
        self.done = False

    def next_chunk(self) -> tuple[None, bool]:
        if not self.done:
            self.output.write(self.request.execute())
            self.done = True
        return None, self.done


class FakeFormsService:
    def __init__(self, responder_url: str):
        self.responder_url = responder_url
        self.batch_calls: list[dict[str, object]] = []
        self.get_calls: list[dict[str, object]] = []

    def forms(self) -> "FakeFormsService":
        return self

    def get(self, *, formId: str) -> FakeRequest:
        self.get_calls.append({"formId": formId})
        if len(self.get_calls) == 1:
            return FakeRequest({"items": [{"itemId": "existing-item"}]})
        return FakeRequest({"responderUri": self.responder_url})

    def batchUpdate(self, **kwargs: object) -> FakeRequest:
        self.batch_calls.append(kwargs)
        return FakeRequest({"replies": []})


class FakeResponsePages:
    def __init__(self, pages: list[dict[str, object]]):
        self.pages = pages
        self.calls: list[dict[str, object]] = []

    def list(self, **kwargs: object) -> FakeRequest:
        self.calls.append(kwargs)
        page_index = len(self.calls) - 1
        return FakeRequest(self.pages[page_index])


class FakeResponseFormsService(FakeFormsService):
    def __init__(self, responder_url: str, form: dict[str, object], pages: list[dict[str, object]]):
        super().__init__(responder_url)
        self.form = form
        self.response_pages = FakeResponsePages(pages)

    def get(self, *, formId: str) -> FakeRequest:
        self.get_calls.append({"formId": formId})
        return FakeRequest(self.form)

    def responses(self) -> FakeResponsePages:
        return self.response_pages


class GoogleFormSchemaTests(TestCase):
    def test_choice_questions_require_multiple_unique_options(self) -> None:
        with self.assertRaises(ValueError):
            GoogleFormQuestion(
                title="Preferred language",
                question_type=GoogleFormQuestionType.multiple_choice,
                options=["Python"],
            )
        with self.assertRaises(ValueError):
            GoogleFormQuestion(
                title="Preferred language",
                question_type=GoogleFormQuestionType.multiple_choice,
                options=["Python", "Python"],
            )

    def test_text_question_rejects_choice_options(self) -> None:
        with self.assertRaises(ValueError):
            GoogleFormQuestion(
                title="Describe your experience",
                question_type=GoogleFormQuestionType.paragraph,
                options=["Option A", "Option B"],
            )

    def test_clone_request_rejects_unknown_fields(self) -> None:
        with self.assertRaises(ValueError):
            GoogleFormCloneRequest(
                title="Data Engineer Application",
                questions=[
                    GoogleFormQuestion(
                        title="Describe your experience",
                        question_type=GoogleFormQuestionType.paragraph,
                    )
                ],
                unexpected="not allowed",
            )


class FormQuestionPromptTests(TestCase):
    def test_prompt_payload_contains_supplied_job_criteria(self) -> None:
        job = JobCreate(
            title="Data Engineer",
            tech_stack="Python, PostgreSQL, Airflow",
            seniority="Senior",
            compensation_min=120000,
            compensation_max=160000,
        )

        payload = build_form_questions_user_prompt(job)

        self.assertIn("Data Engineer", payload)
        self.assertIn("PostgreSQL", payload)
        self.assertIn("Airflow", payload)
        self.assertIn("role-specific", FORM_QUESTION_SYSTEM_PROMPT.lower())
        self.assertIn("fixed question list", FORM_QUESTION_SYSTEM_PROMPT.lower())


class FakeTextAIProvider:
    def __init__(self, response: object):
        self.response = response
        self.calls: list[dict[str, object]] = []

    def generate_structured(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class FormQuestionGenerationTests(TestCase):
    def test_generated_questions_are_passed_to_cloned_form(self) -> None:
        questions = [
            GoogleFormQuestion(
                title="How have you used Airflow to orchestrate production pipelines?",
                question_type=GoogleFormQuestionType.paragraph,
            ),
            GoogleFormQuestion(
                title="Which SQL databases have you used at scale?",
                question_type=GoogleFormQuestionType.multiple_choice,
                options=["PostgreSQL", "MySQL", "Other"],
            ),
        ]
        question_set = GoogleFormQuestionSet(questions=questions)
        provider = FakeTextAIProvider(question_set)
        drive_files = FakeDriveFiles({"id": "copied-form-id"})
        drive = FakeDriveService(drive_files)
        forms = FakeFormsService(
            "https://docs.google.com/forms/d/copied-form-id/viewform"
        )
        settings = Settings(
            _env_file=None,
            google_form_template_id="template-id",
            google_drive_folder_id="folder-id",
        )
        service = GoogleFormsService(
            settings_provider=lambda: settings,
            drive_service=drive,
            forms_service=forms,
        )
        job = JobCreate(
            title="Data Engineer",
            tech_stack="Python, PostgreSQL, Airflow",
            seniority="Senior",
        )

        result = service.generate_and_clone_application_form(job, provider)

        self.assertEqual(
            str(result.responder_url),
            "https://docs.google.com/forms/d/copied-form-id/viewform",
        )
        self.assertIn("Airflow", provider.calls[0]["user_content"])
        request_items = forms.batch_calls[0]["body"]["requests"]
        self.assertEqual(len(request_items), 5)


class GoogleFormsServiceTests(TestCase):
    def setUp(self) -> None:
        self.drive_files = FakeDriveFiles({"id": "copied-form-id"})
        self.drive = FakeDriveService(self.drive_files)
        self.forms = FakeFormsService(
            "https://docs.google.com/forms/d/copied-form-id/viewform"
        )
        self.service = GoogleFormsService(
            drive_service=self.drive,
            forms_service=self.forms,
        )

    def test_clones_form_and_appends_typed_questions(self) -> None:
        request = GoogleFormCloneRequest(
            template_file_id="template-id",
            destination_folder_id="folder-id",
            title="Data Engineer Application",
            questions=[
                GoogleFormQuestion(
                    title="Describe your production Python experience",
                    question_type=GoogleFormQuestionType.paragraph,
                ),
                GoogleFormQuestion(
                    title="Which database have you used?",
                    question_type=GoogleFormQuestionType.multiple_choice,
                    options=["PostgreSQL", "MySQL"],
                ),
            ],
        )

        result = self.service.clone_application_form(request)

        self.assertIsInstance(result, GoogleFormCloneResult)
        self.assertEqual(result.form_id, "copied-form-id")
        self.assertEqual(
            str(result.responder_url),
            "https://docs.google.com/forms/d/copied-form-id/viewform",
        )
        self.assertEqual(
            self.drive_files.copy_calls[0]["fileId"], "template-id"
        )
        self.assertEqual(
            self.drive_files.copy_calls[0]["body"],
            {
                "name": "Data Engineer Application",
                "parents": ["folder-id"],
            },
        )

        requests = self.forms.batch_calls[0]["body"]["requests"]
        self.assertEqual(requests[0]["updateFormInfo"]["info"]["title"], "Data Engineer Application")
        self.assertEqual(requests[0]["updateFormInfo"]["updateMask"], "title")
        self.assertEqual(requests[1]["createItem"]["item"]["title"], "Full name")
        self.assertEqual(requests[2]["createItem"]["item"]["title"], "Email address")
        self.assertEqual(requests[3]["createItem"]["location"]["index"], 3)
        self.assertEqual(
            requests[3]["createItem"]["item"]["questionItem"]["question"]["textQuestion"],
            {"paragraph": True},
        )
        self.assertEqual(requests[4]["createItem"]["location"]["index"], 4)
        self.assertEqual(
            requests[4]["createItem"]["item"]["questionItem"]["question"]["choiceQuestion"]["type"],
            "RADIO",
        )

    def test_service_uses_global_template_and_folder_settings(self) -> None:
        settings = Settings(
            _env_file=None,
            google_form_template_id="configured-template",
            google_drive_folder_id="configured-folder",
        )
        service = GoogleFormsService(
            settings_provider=lambda: settings,
            drive_service=self.drive,
            forms_service=self.forms,
        )
        request = GoogleFormCloneRequest(
            title="Configured Form",
            questions=[
                GoogleFormQuestion(
                    title="Tell us about your experience",
                    question_type=GoogleFormQuestionType.paragraph,
                )
            ],
        )

        service.clone_application_form(request)

        self.assertEqual(self.drive_files.copy_calls[0]["fileId"], "configured-template")
        self.assertEqual(
            self.drive_files.copy_calls[0]["body"]["parents"], ["configured-folder"]
        )

    def test_missing_template_or_credentials_fails_before_api_call(self) -> None:
        settings = Settings(_env_file=None)
        service = GoogleFormsService(settings_provider=lambda: settings)
        request = GoogleFormCloneRequest(
            title="Data Engineer Application",
            questions=[
                GoogleFormQuestion(
                    title="Describe your experience",
                    question_type=GoogleFormQuestionType.paragraph,
                )
            ],
        )

        with self.assertRaises(GoogleFormsConfigurationError):
            service.clone_application_form(request)

    def test_oauth_reconsents_when_cached_token_lacks_response_scope(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            client_file = root / "oauth-client.json"
            token_file = root / "oauth-token.json"
            client_file.write_text("{}", encoding="utf-8")
            token_file.write_text("{}", encoding="utf-8")
            settings = Settings(
                _env_file=None,
                google_oauth_client_file=client_file,
                google_oauth_token_file=token_file,
            )
            old_credentials = SimpleNamespace(
                valid=True,
                expired=False,
                refresh_token="refresh-token",
                scopes=["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/forms.body"],
            )
            refreshed_credentials = SimpleNamespace(
                valid=True,
                expired=False,
                refresh_token="new-refresh-token",
                scopes=[
                    "https://www.googleapis.com/auth/drive",
                    "https://www.googleapis.com/auth/forms.body",
                    "https://www.googleapis.com/auth/forms.responses.readonly",
                ],
                to_json=lambda: '{"token":"new"}',
            )
            flow = Mock()
            flow.run_local_server.return_value = refreshed_credentials
            service = GoogleFormsService(
                settings_provider=lambda: settings,
                oauth_flow_factory=lambda *args, **kwargs: flow,
            )

            with patch(
                "app.services.google_forms.OAuthCredentials.from_authorized_user_file",
                return_value=old_credentials,
            ):
                credentials = service._load_oauth_credentials(
                    settings,
                    scopes=(
                        "https://www.googleapis.com/auth/drive",
                        "https://www.googleapis.com/auth/forms.body",
                        "https://www.googleapis.com/auth/forms.responses.readonly",
                    ),
                )

            self.assertIs(credentials, refreshed_credentials)
            flow.run_local_server.assert_called_once()
            self.assertEqual(token_file.read_text(encoding="utf-8"), '{"token":"new"}')

    def test_oauth_refresh_failure_falls_back_to_consent(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            client_file = root / "oauth-client.json"
            token_file = root / "oauth-token.json"
            client_file.write_text("{}", encoding="utf-8")
            token_file.write_text("{}", encoding="utf-8")
            settings = Settings(
                _env_file=None,
                google_oauth_client_file=client_file,
                google_oauth_token_file=token_file,
            )
            expired_credentials = Mock()
            expired_credentials.valid = False
            expired_credentials.expired = True
            expired_credentials.refresh_token = "refresh-token"
            expired_credentials.scopes = [
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/forms.body",
            ]
            expired_credentials.refresh.side_effect = RuntimeError("refresh rejected")
            refreshed_credentials = SimpleNamespace(
                valid=True,
                expired=False,
                refresh_token="new-refresh-token",
                scopes=expired_credentials.scopes,
                to_json=lambda: '{"token":"new"}',
            )
            flow = Mock()
            flow.run_local_server.return_value = refreshed_credentials
            service = GoogleFormsService(
                settings_provider=lambda: settings,
                oauth_flow_factory=lambda *args, **kwargs: flow,
            )

            with patch(
                "app.services.google_forms.OAuthCredentials.from_authorized_user_file",
                return_value=expired_credentials,
            ):
                credentials = service._load_oauth_credentials(settings)

            self.assertIs(credentials, refreshed_credentials)
            expired_credentials.refresh.assert_called_once()
            flow.run_local_server.assert_called_once()

    def test_clone_and_response_read_request_separate_google_scopes(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            service_account = Path(temporary_directory) / "service-account.json"
            service_account.write_text("{}", encoding="utf-8")
            settings = Settings(
                _env_file=None,
                google_service_account_file=service_account,
            )
            credential_factory = Mock(return_value=object())
            service_builder = Mock(return_value=object())

            clone_service = GoogleFormsService(
                settings_provider=lambda: settings,
                credentials_factory=credential_factory,
                service_builder=service_builder,
            )
            clone_service._get_services(settings)
            clone_scopes = credential_factory.call_args.kwargs["scopes"]

            response_service = GoogleFormsService(
                settings_provider=lambda: settings,
                credentials_factory=credential_factory,
                service_builder=service_builder,
            )
            response_service._get_services(
                settings,
                scopes=(
                    "https://www.googleapis.com/auth/drive",
                    "https://www.googleapis.com/auth/forms.body",
                    "https://www.googleapis.com/auth/forms.responses.readonly",
                ),
            )
            response_scopes = credential_factory.call_args.kwargs["scopes"]

        self.assertEqual(
            clone_scopes,
            [
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/forms.body",
            ],
        )
        self.assertEqual(len(response_scopes), 3)

    def test_google_api_error_is_sanitized(self) -> None:
        files = FakeDriveFiles(
            {"id": ""},
            error=RuntimeError("sensitive provider response payload"),
        )
        service = GoogleFormsService(
            drive_service=FakeDriveService(files),
            forms_service=self.forms,
        )
        request = GoogleFormCloneRequest(
            template_file_id="template-id",
            title="Data Engineer Application",
            questions=[
                GoogleFormQuestion(
                    title="Describe your experience",
                    question_type=GoogleFormQuestionType.paragraph,
                )
            ],
        )

        with self.assertRaises(GoogleFormsIntegrationError) as raised:
            service.clone_application_form(request)

        self.assertNotIn("sensitive provider response", str(raised.exception))

    def test_lists_all_form_responses_with_question_titles_and_pdf_uploads(self) -> None:
        forms = FakeResponseFormsService(
            "https://forms.example/apply",
            {
                "items": [
                    {
                        "title": "What is your full name?",
                        "questionItem": {"question": {"questionId": "name-q"}},
                    },
                    {
                        "title": "Resume",
                        "questionItem": {"question": {"questionId": "resume-q"}},
                    },
                    {
                        "title": "Years of experience",
                        "questionItem": {"question": {"questionId": "years-q"}},
                    },
                ]
            },
            [
                {
                    "responses": [
                        {
                            "responseId": "response-1",
                            "respondentEmail": "sam@example.com",
                            "answers": {
                                "name-q": {"textAnswers": {"answers": [{"value": "Sam Example"}]}},
                                "resume-q": {"fileUploadAnswers": {"answers": [{"fileId": "drive-file-1", "fileName": "Sam", "mimeType": "application/pdf"}]}},
                                "years-q": {"textAnswers": {"answers": [{"value": "8"}]}},
                            },
                        }
                    ],
                    "nextPageToken": "next-page",
                },
                {
                    "responses": [
                        {
                            "responseId": "response-2",
                            "respondentEmail": "lee@example.com",
                            "answers": {
                                "name-q": {"textAnswers": {"answers": [{"value": "Lee Example"}]}},
                                "resume-q": {"fileUploadAnswers": {"answers": [{"fileId": "drive-file-2", "fileName": "Lee.pdf"}]}},
                                "years-q": {"textAnswers": {"answers": [{"value": "5"}]}},
                            },
                        }
                    ]
                },
            ],
        )
        service = GoogleFormsService(
            settings_provider=lambda: Settings(_env_file=None),
            drive_service=self.drive,
            forms_service=forms,
        )

        submissions = service.list_application_responses("form-id")

        self.assertEqual(len(submissions), 2)
        self.assertEqual(submissions[0].response_id, "response-1")
        self.assertEqual(submissions[0].applicant_name, "Sam Example")
        self.assertEqual(submissions[0].email, "sam@example.com")
        self.assertEqual(submissions[0].answers["Years of experience"], "8")
        self.assertEqual(submissions[0].resume_files[0].file_id, "drive-file-1")
        self.assertEqual(submissions[0].resume_files[0].mime_type, "application/pdf")
        self.assertEqual(forms.response_pages.calls[1]["pageToken"], "next-page")

    def test_extracts_pdf_resume_text_from_drive_upload(self) -> None:
        submission = GoogleFormSubmission(
            response_id="response-1",
            applicant_name="Sam Example",
            email="sam@example.com",
            answers={"Resume": "Sam.pdf"},
            resume_files=[
                GoogleFormUploadedFile(file_id="drive-file-1", file_name="Sam.pdf")
            ],
        )
        files = FakeDriveFiles({"id": "unused"})
        service = GoogleFormsService(
            settings_provider=lambda: Settings(_env_file=None),
            drive_service=FakeDriveService(files),
            forms_service=self.forms,
        )

        with (
            patch("app.services.google_forms.PdfReader") as pdf_reader,
            patch(
                "app.services.google_forms.MediaIoBaseDownload",
                FakeMediaIoBaseDownload,
            ),
        ):
            pdf_reader.return_value.pages = [
                type("Page", (), {"extract_text": lambda self: "Python engineer"})(),
                type("Page", (), {"extract_text": lambda self: "PostgreSQL"})(),
            ]
            text = service.extract_resume_text(submission)

        self.assertEqual(text, "Python engineer\nPostgreSQL")
        self.assertEqual(
            files.download_calls[0], {"fileId": "drive-file-1"}
        )

    def test_extracts_pdf_identified_by_mime_type_without_extension(self) -> None:
        submission = GoogleFormSubmission(
            response_id="response-1",
            applicant_name="Sam Example",
            email="sam@example.com",
            answers={"Resume": "resume"},
            resume_files=[
                GoogleFormUploadedFile(
                    file_id="drive-file-1",
                    file_name="resume",
                    mime_type="application/pdf",
                )
            ],
        )
        files = FakeDriveFiles({"id": "unused"})
        service = GoogleFormsService(
            settings_provider=lambda: Settings(_env_file=None),
            drive_service=FakeDriveService(files),
            forms_service=self.forms,
        )

        with (
            patch("app.services.google_forms.PdfReader") as pdf_reader,
            patch(
                "app.services.google_forms.MediaIoBaseDownload",
                FakeMediaIoBaseDownload,
            ),
        ):
            pdf_reader.return_value.pages = [
                type("Page", (), {"extract_text": lambda self: "Python engineer"})()
            ]
            text = service.extract_resume_text(submission)

        self.assertEqual(text, "Python engineer")
        self.assertEqual(
            files.download_calls[0], {"fileId": "drive-file-1"}
        )


class LocalMediaServiceTests(TestCase):
    def test_stores_and_verifies_interview_recording(self) -> None:
        interview_id = uuid4()
        with TemporaryDirectory() as temporary_directory:
            result = store_interview_recording(
                BytesIO(b"recording bytes are stored without decoding"),
                interview_id=interview_id,
                job_title="Data Engineer",
                candidate_name="Alex Doe",
                interview_date=date(2026, 10, 1),
                sequence_order=2,
                recordings_root=Path(temporary_directory),
            )

            self.assertEqual(result.interview_id, interview_id)
            self.assertEqual(result.sequence_order, 2)
            self.assertTrue(result.recording_verified)
            self.assertTrue(Path(result.local_audio_path).is_file())
            self.assertIn("technical_interview_2.mp3", result.local_audio_path)


class FormSyncServiceTests(TestCase):
    def setUp(self) -> None:
        self.job = SimpleNamespace(
            id=uuid4(),
            title="Data Engineer",
            google_form_id="form-id",
            jd_markdown="Must have production Python experience.",
        )
        self.submission = GoogleFormSubmission(
            response_id="response-1",
            applicant_name="Sam Example",
            email="sam@example.com",
            answers={
                "Email address": "sam@example.com",
                "Contact Number": "+15551234567",
                "Years using Python?": "8 years",
            },
            resume_files=[
                GoogleFormUploadedFile(file_id="resume-1", file_name="Sam.pdf")
            ],
        )
        self.forms = Mock()
        self.forms.list_application_responses.return_value = [self.submission]
        self.forms.extract_resume_text.return_value = "Sam Example built Python services."
        self.provider = Mock()
        self.provider.generate_structured.return_value = ApplicationScreeningResult(
            agent_decision=ScreeningDecision.passed,
            screening_summary="Evidence supports production Python experience.",
        )

    def test_sync_screens_and_persists_all_answers(self) -> None:
        candidate = SimpleNamespace(
            id=uuid4(), full_name="Sam Example", email="sam@example.com"
        )
        application = SimpleNamespace(
            id=uuid4(), pipeline_status=PipelineStatus.active_pipeline
        )
        with (
            patch("app.services.form_sync_service.candidates_db.get_application_for_form_response", return_value=None),
            patch("app.services.form_sync_service.candidates_db.find_candidate_by_identity", return_value=None),
            patch("app.services.form_sync_service.candidates_db.create_candidate", return_value=candidate) as create_candidate,
            patch("app.services.form_sync_service.candidates_db.create_screened_application", return_value=application) as save_application,
        ):
            result = sync_form_responses(
                self.job,
                forms_service=self.forms,
                ai_provider=self.provider,
            )

        self.assertEqual(result.synced, 1)
        self.assertEqual(result.items[0].status, FormSyncItemStatus.synced)
        self.assertEqual(result.items[0].agent_decision, ScreeningDecision.passed)
        self.assertEqual(
            save_application.call_args.kwargs["form_responses"],
            {
                "Email address": "sam@example.com",
                "Contact Number": "+15551234567",
                "Years using Python?": "8 years",
            },
        )
        self.assertEqual(
            create_candidate.call_args.args[0].phone,
            "+15551234567",
        )
        screening_input = self.provider.generate_structured.call_args.kwargs["user_content"]
        self.assertIn("Years using Python?", screening_input)
        self.assertNotIn("sam@example.com", screening_input)
        self.assertIn("[EMAIL]", screening_input)

    def test_sync_skips_an_already_saved_form_response(self) -> None:
        existing = SimpleNamespace(
            id=uuid4(),
            agent_decision=ScreeningDecision.passed,
            pipeline_status=PipelineStatus.active_pipeline,
            screening_summary="Previously screened.",
        )
        with patch(
            "app.services.form_sync_service.candidates_db.get_application_for_form_response",
            return_value=existing,
        ):
            result = sync_form_responses(
                self.job,
                forms_service=self.forms,
                ai_provider=self.provider,
            )

        self.assertEqual(result.skipped_duplicates, 1)
        self.assertEqual(result.items[0].status, FormSyncItemStatus.duplicate)
        self.forms.extract_resume_text.assert_not_called()
        self.provider.generate_structured.assert_not_called()

    def test_sync_reports_safe_resume_extraction_error(self) -> None:
        self.forms.extract_resume_text.side_effect = GoogleFormsIntegrationError(
            "Uploaded PDF contains no extractable text"
        )
        with (
            patch("app.services.form_sync_service.candidates_db.get_application_for_form_response", return_value=None),
            patch("app.services.form_sync_service.candidates_db.find_candidate_by_identity", return_value=None),
        ):
            result = sync_form_responses(
                self.job,
                forms_service=self.forms,
                ai_provider=self.provider,
            )

        self.assertEqual(result.errors, 1)
        self.assertEqual(
            result.items[0].detail,
            "Uploaded PDF contains no extractable text",
        )
