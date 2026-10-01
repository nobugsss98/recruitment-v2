from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api import deps as deps_module
from app.api.v1 import jobs as jobs_router
from app.main import app
from app.schemas.auth_schema import UserRead, UserRole
from app.schemas.jobs_schema import JobCreate, JobPatch, JobRead, JobStatus
from app.schemas.candidates_schema import FormSyncResult
from app.services.google_forms import GoogleFormsConfigurationError


def make_user(role: UserRole = UserRole.hr) -> UserRead:
    return UserRead(
        id=uuid4(),
        email="hr@example.com",
        full_name="HR Admin",
        role=role,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )


class FakeJobsDb:
    def __init__(self):
        self.jobs: dict[str, JobRead] = {}

    def create_job(self, job: JobCreate) -> JobRead:
        row = JobRead(
            id=uuid4(),
            title=job.title,
            tech_stack=job.tech_stack,
            seniority=job.seniority,
            compensation_min=job.compensation_min,
            compensation_max=job.compensation_max,
            jd_markdown=None,
            google_form_id=None,
            google_form_url=None,
            linkedin_blurb=None,
            status=JobStatus.draft,
            created_at=datetime.now(timezone.utc),
        )
        self.jobs[str(row.id)] = row
        return row

    def list_jobs(self, *, status: JobStatus | None = None) -> list[JobRead]:
        rows = list(self.jobs.values())
        if status is not None:
            rows = [row for row in rows if row.status == status]
        return sorted(rows, key=lambda item: item.created_at, reverse=True)

    def get_job(self, job_id):
        return self.jobs.get(str(job_id))

    def update_job(self, job_id, patch: JobPatch):
        row = self.jobs[str(job_id)]
        values = patch.model_dump(exclude_unset=True)
        for key, value in values.items():
            setattr(row, key, value)
        return row


class JobsApiTests(TestCase):
    def setUp(self) -> None:
        self.store = FakeJobsDb()
        jobs_router.get_jobs_store = lambda: self.store
        self.hr_user = make_user(UserRole.hr)
        app.dependency_overrides[deps_module.get_current_user] = lambda: self.hr_user
        self.audit_patch = patch("app.services.audit.record_audit")
        self.audit_mock = self.audit_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.audit_patch.stop()
        app.dependency_overrides.clear()

    def test_create_job_returns_201_and_job_payload(self) -> None:
        response = self.client.post(
            "/api/v1/jobs",
            json={
                "title": "Data Engineer",
                "tech_stack": "Python, Postgres",
                "seniority": "Senior",
                "compensation_min": 110000,
                "compensation_max": 150000,
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["title"], "Data Engineer")
        self.assertEqual(payload["status"], "draft")
        self.audit_mock.assert_called_once()
        self.assertEqual(self.audit_mock.call_args.kwargs["action"], "job_created")

    def test_list_jobs_is_available_to_any_authenticated_role(self) -> None:
        app.dependency_overrides[deps_module.get_current_user] = lambda: make_user(UserRole.interviewer)
        response = self.client.get("/api/v1/jobs")
        self.assertEqual(response.status_code, 200)

    def test_patch_job_updates_fields(self) -> None:
        created = self.store.create_job(
            JobCreate(
                title="Data Scientist",
                tech_stack="Python, SQL",
                seniority="Mid",
            )
        )

        response = self.client.patch(
            f"/api/v1/jobs/{created.id}",
            json={"status": "posted", "jd_markdown": "# JD"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "posted")
        self.assertEqual(payload["jd_markdown"], "# JD")

    def test_linkedin_blurb_requires_form_and_jd(self) -> None:
        created = self.store.create_job(
            JobCreate(title="Data Scientist", tech_stack="Python", seniority="Mid")
        )

        response = self.client.post(f"/api/v1/jobs/{created.id}/linkedin-blurb")

        self.assertEqual(response.status_code, 409)

    def test_linkedin_blurb_persists_provider_output_and_form_url(self) -> None:
        created = self.store.create_job(
            JobCreate(title="Data Scientist", tech_stack="Python", seniority="Mid")
        )
        self.store.update_job(
            created.id,
            JobPatch(jd_markdown="# Data Scientist", google_form_url="https://forms.example/apply"),
        )

        provider = Mock()
        provider.generate_text.return_value = "Apply here: https://forms.example/apply"
        with patch.object(jobs_router, "get_ai_provider", return_value=provider):
            response = self.client.post(f"/api/v1/jobs/{created.id}/linkedin-blurb")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["linkedin_blurb"], "Apply here: https://forms.example/apply")
        provider.generate_text.assert_called_once()

    def test_sync_runs_form_batch_without_manual_applicant_payload(self) -> None:
        created = self.store.create_job(
            JobCreate(title="Data Scientist", tech_stack="Python", seniority="Mid")
        )
        self.store.update_job(
            created.id,
            JobPatch(
                jd_markdown="# Data Scientist",
                google_form_id="form-id",
                google_form_url="https://forms.example/apply",
            ),
        )
        result = FormSyncResult(
            total_responses=2,
            synced=1,
            skipped_duplicates=1,
            errors=0,
            items=[],
        )

        with patch.object(jobs_router, "GoogleFormsService") as forms_service:
            with patch.object(jobs_router, "get_ai_provider", return_value=Mock()):
                with patch.object(jobs_router, "sync_form_responses", return_value=result) as sync:
                    response = self.client.post(f"/api/v1/jobs/{created.id}/sync")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_responses"], 2)
        forms_service.assert_called_once()
        sync.assert_called_once()
        self.audit_mock.assert_called_once()
        self.assertEqual(self.audit_mock.call_args.kwargs["action"], "sync_run")

    def test_clone_form_configuration_error_returns_service_unavailable(self) -> None:
        created = self.store.create_job(
            JobCreate(title="Data Scientist", tech_stack="Python", seniority="Mid")
        )
        with patch.object(jobs_router, "GoogleFormsService") as forms_service:
            forms_service.return_value.clone_application_form.side_effect = (
                GoogleFormsConfigurationError("Google client initialization failed")
            )
            response = self.client.post(
                f"/api/v1/jobs/{created.id}/clone-form",
                json={
                    "questions": [
                        {"title": "Describe your experience", "question_type": "paragraph"},
                        {"title": "Which tools have you used?", "question_type": "short_text"},
                    ]
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Google client initialization failed")

    def test_interviewer_cannot_create_job(self) -> None:
        app.dependency_overrides[deps_module.get_current_user] = lambda: make_user(UserRole.interviewer)
        response = self.client.post(
            "/api/v1/jobs",
            json={"title": "Data Engineer", "tech_stack": "Python", "seniority": "Senior"},
        )
        self.assertEqual(response.status_code, 403)
