from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID, uuid4

from pydantic import AnyHttpUrl, SecretStr

from app.config import Settings
from app.database.crud import candidates_db, interviews_db, jobs_db
from app.database.crud.errors import (
    AmbiguousCandidateMatchError,
    DatabaseOperationError,
)
from app.schemas.candidates_schema import (
    ApplicationCreate,
    ApplicationApplicantRead,
    ApplicationDashboardRecord,
    CandidateCreate,
    CandidateIdentityLookup,
    ApplicationScreeningResult,
    PipelineStatus,
    ScreeningDecision,
)
from app.schemas.interviews_schema import (
    InterviewRecordingResult,
    InterviewRoundUpdate,
    InterviewScheduleRequest,
)
from app.schemas.jobs_schema import JobCreate, JobPatch, JobStatus
from app.services.supabase_service import (
    LazySupabaseClient,
    SupabaseConfigurationError,
)


class FakeQuery:
    def __init__(self, client: "FakeSupabaseClient", table_name: str, data: object):
        self.client = client
        self.table_name = table_name
        self.data = data

    def select(self, columns: str = "*") -> "FakeQuery":
        self.client.events.append((self.table_name, "select", columns))
        return self

    def insert(self, values: dict[str, object]) -> "FakeQuery":
        self.client.events.append((self.table_name, "insert", values))
        return self

    def update(self, values: dict[str, object]) -> "FakeQuery":
        self.client.events.append((self.table_name, "update", values))
        return self

    def delete(self) -> "FakeQuery":
        self.client.events.append((self.table_name, "delete"))
        return self

    def eq(self, column: str, value: object) -> "FakeQuery":
        self.client.events.append((self.table_name, "eq", column, value))
        return self

    def ilike(self, column: str, value: str) -> "FakeQuery":
        self.client.events.append((self.table_name, "ilike", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> "FakeQuery":
        self.client.events.append((self.table_name, "order", column, desc))
        return self

    def limit(self, count: int) -> "FakeQuery":
        self.client.events.append((self.table_name, "limit", count))
        return self

    def execute(self) -> SimpleNamespace:
        self.client.events.append((self.table_name, "execute"))
        if isinstance(self.data, Exception):
            raise self.data
        return SimpleNamespace(data=self.data)


class FakeSupabaseClient:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.events: list[tuple[object, ...]] = []

    def table(self, table_name: str) -> FakeQuery:
        self.events.append(("table", table_name))
        response = self.responses.pop(0)
        return FakeQuery(self, table_name, response)


def job_row() -> dict[str, object]:
    return {
        "id": uuid4(),
        "title": "Data Engineer",
        "tech_stack": "Python, PostgreSQL",
        "seniority": "Senior",
        "compensation_min": "120000.00",
        "compensation_max": "160000.00",
        "jd_markdown": None,
        "google_form_id": None,
        "google_form_url": None,
        "linkedin_blurb": None,
        "status": "draft",
        "created_at": datetime(2026, 9, 29, tzinfo=timezone.utc),
    }


def candidate_row(candidate_id: UUID | None = None) -> dict[str, object]:
    return {
        "id": candidate_id or uuid4(),
        "full_name": "Alex Doe",
        "email": "alex@example.com",
        "phone": "+15551234567",
        "linkedin_url": "https://www.linkedin.com/in/alex-doe",
        "created_at": datetime(2026, 9, 29, tzinfo=timezone.utc),
    }


def application_row(
    candidate_id: UUID | None = None,
    job_id: UUID | None = None,
) -> dict[str, object]:
    return {
        "id": uuid4(),
        "candidate_id": candidate_id or uuid4(),
        "job_id": job_id or uuid4(),
        "current_stage": "sync_evaluation",
        "agent_decision": None,
        "screening_summary": None,
        "hr_override_status": None,
        "examiner": "agent",
        "pipeline_status": "failed_at_sync",
        "final_decision": "pending",
        "remarks": None,
        "created_at": datetime(2026, 9, 29, tzinfo=timezone.utc),
    }


def interview_row(
    application_id: UUID,
    *,
    sequence_order: int = 1,
) -> dict[str, object]:
    return {
        "id": uuid4(),
        "application_id": application_id,
        "sequence_order": sequence_order,
        "scheduled_at": datetime(2026, 10, 1, 15, tzinfo=timezone.utc),
        "interview_date": None,
        "local_audio_path": None,
        "feedback": None,
        "status": "pending",
        "created_at": datetime(2026, 9, 29, tzinfo=timezone.utc),
    }


class SupabaseServiceTests(TestCase):
    def test_client_is_created_lazily_and_reused(self) -> None:
        settings = Settings(
            _env_file=None,
            supabase_url="https://project.supabase.co",
            supabase_service_role_key=SecretStr("service-role-test-key"),
        )
        client = FakeSupabaseClient([[], []])
        factory_calls: list[tuple[str, str]] = []

        def client_factory(url: str, key: str) -> FakeSupabaseClient:
            factory_calls.append((url, key))
            return client

        lazy_client = LazySupabaseClient(
            settings_provider=lambda: settings,
            client_factory=client_factory,
        )

        lazy_client.table("jobs")
        lazy_client.table("candidates")

        self.assertEqual(len(factory_calls), 1)
        self.assertEqual(factory_calls[0], ("https://project.supabase.co/", "service-role-test-key"))

    def test_missing_supabase_configuration_fails_on_first_use(self) -> None:
        settings = Settings(_env_file=None)
        lazy_client = LazySupabaseClient(settings_provider=lambda: settings)

        with self.assertRaises(SupabaseConfigurationError):
            lazy_client.table("jobs")


class JobCrudTests(TestCase):
    def test_create_job_returns_validated_model(self) -> None:
        row = job_row()
        client = FakeSupabaseClient([[row]])
        payload = JobCreate(
            title="Data Engineer",
            tech_stack="Python, PostgreSQL",
            seniority="Senior",
        )

        with patch.object(jobs_db, "supabase_client", client):
            job = jobs_db.create_job(payload)

        self.assertEqual(job.id, row["id"])
        self.assertIn(("jobs", "insert", payload.model_dump(mode="json")), client.events)

    def test_get_job_returns_validated_model(self) -> None:
        row = job_row()
        client = FakeSupabaseClient([[row]])

        with patch.object(jobs_db, "supabase_client", client):
            job = jobs_db.get_job(row["id"])

        self.assertEqual(job.id, row["id"])

    def test_list_jobs_filters_status_and_orders_newest_first(self) -> None:
        row = job_row()
        client = FakeSupabaseClient([[row]])

        with patch.object(jobs_db, "supabase_client", client):
            jobs = jobs_db.list_jobs(status=JobStatus.posted)

        self.assertEqual(len(jobs), 1)
        self.assertIn(("jobs", "eq", "status", "posted"), client.events)
        self.assertIn(("jobs", "order", "created_at", True), client.events)

    def test_update_job_returns_none_when_id_is_missing(self) -> None:
        client = FakeSupabaseClient([[]])

        with patch.object(jobs_db, "supabase_client", client):
            job = jobs_db.update_job(uuid4(), JobPatch(status=JobStatus.closed))

        self.assertIsNone(job)


class CandidateCrudTests(TestCase):
    def test_create_candidate_returns_validated_model(self) -> None:
        row = candidate_row()
        client = FakeSupabaseClient([[row]])
        payload = CandidateCreate(
            full_name="Alex Doe",
            email="alex@example.com",
            phone="+15551234567",
            linkedin_url="https://www.linkedin.com/in/alex-doe",
        )

        with patch.object(candidates_db, "supabase_client", client):
            candidate = candidates_db.create_candidate(payload)

        self.assertEqual(candidate.id, row["id"])
        self.assertIn(("candidates", "insert", payload.model_dump(mode="json")), client.events)

    def test_candidate_lookup_matches_normalized_email(self) -> None:
        row = candidate_row()
        client = FakeSupabaseClient([[row]])
        identity = CandidateIdentityLookup(email="ALEX@example.com")

        with patch.object(candidates_db, "supabase_client", client):
            candidate = candidates_db.find_candidate_by_identity(identity)

        self.assertEqual(candidate.id, row["id"])
        self.assertIn(
            ("candidates", "ilike", "email", "alex@example.com"), client.events
        )

    def test_identity_keys_matching_different_people_are_rejected(self) -> None:
        first_id = uuid4()
        second_id = uuid4()
        client = FakeSupabaseClient(
            [[candidate_row(first_id)], [candidate_row(second_id)]]
        )
        identity = CandidateIdentityLookup(
            email="alex@example.com",
            phone="+15551234567",
        )

        with patch.object(candidates_db, "supabase_client", client):
            with self.assertRaises(AmbiguousCandidateMatchError):
                candidates_db.find_candidate_by_identity(identity)

    def test_create_application_uses_only_candidate_and_job_ids(self) -> None:
        candidate_id = uuid4()
        job_id = uuid4()
        row = application_row(candidate_id, job_id)
        client = FakeSupabaseClient([[row]])
        payload = ApplicationCreate(candidate_id=candidate_id, job_id=job_id)

        with patch.object(candidates_db, "supabase_client", client):
            application = candidates_db.create_application(payload)

        self.assertEqual(application.candidate_id, candidate_id)
        self.assertEqual(application.job_id, job_id)
        self.assertIn(
            (
                "applications",
                "insert",
                {"candidate_id": str(candidate_id), "job_id": str(job_id)},
            ),
            client.events,
        )

    def test_get_application_for_candidate_and_job(self) -> None:
        candidate_id = uuid4()
        job_id = uuid4()
        row = application_row(candidate_id, job_id)
        client = FakeSupabaseClient([[row]])

        with patch.object(candidates_db, "supabase_client", client):
            application = candidates_db.get_application_for_candidate_job(
                candidate_id, job_id
            )

        self.assertEqual(application.id, row["id"])

    def test_get_application_for_form_response(self) -> None:
        row = application_row()
        row["google_form_response_id"] = "forms-response-1"
        row["form_responses"] = {"Experience": "8 years"}
        client = FakeSupabaseClient([[row]])

        with patch.object(candidates_db, "supabase_client", client):
            application = candidates_db.get_application_for_form_response(
                row["job_id"], "forms-response-1"
            )

        self.assertEqual(application.google_form_response_id, "forms-response-1")
        self.assertIn(
            ("applications", "eq", "google_form_response_id", "forms-response-1"),
            client.events,
        )

    def test_list_job_applications_includes_candidate_and_form_answers(self) -> None:
        row = application_row()
        candidate = candidate_row(row["candidate_id"])
        row["google_form_response_id"] = "forms-response-1"
        row["form_responses"] = {"Experience": "8 years"}
        row["candidates"] = {
            "full_name": candidate["full_name"],
            "email": candidate["email"],
            "phone": candidate["phone"],
        }
        client = FakeSupabaseClient([[row]])

        with patch.object(candidates_db, "supabase_client", client):
            applications = candidates_db.list_job_applications(row["job_id"])

        self.assertIsInstance(applications[0], ApplicationApplicantRead)
        self.assertEqual(applications[0].candidate_name, "Alex Doe")
        self.assertEqual(applications[0].email, "alex@example.com")
        self.assertEqual(applications[0].phone, "+15551234567")
        self.assertEqual(applications[0].form_responses, {"Experience": "8 years"})
        self.assertIn(
            ("applications", "select", "*, candidates(full_name,email,phone)"),
            client.events,
        )

    def test_create_screened_application_saves_answers_and_response_id(self) -> None:
        row = application_row()
        row.update(
            {
                "google_form_response_id": "forms-response-1",
                "form_responses": {"Experience": "8 years"},
                "agent_decision": "pass",
                "screening_summary": "Evidence supports the required experience.",
                "pipeline_status": "active_pipeline",
                "final_decision": "pending",
            }
        )
        client = FakeSupabaseClient([[row]])

        with patch.object(candidates_db, "supabase_client", client):
            application = candidates_db.create_screened_application(
                ApplicationCreate(candidate_id=row["candidate_id"], job_id=row["job_id"]),
                response_id="forms-response-1",
                form_responses={"Experience": "8 years"},
                screening=ApplicationScreeningResult(
                    agent_decision=ScreeningDecision.passed,
                    screening_summary="Evidence supports the required experience.",
                ),
            )

        insert_event = next(event for event in client.events if event[1] == "insert")
        self.assertEqual(insert_event[2]["google_form_response_id"], "forms-response-1")
        self.assertEqual(insert_event[2]["form_responses"], {"Experience": "8 years"})
        self.assertEqual(application.pipeline_status, PipelineStatus.active_pipeline)


    def test_candidate_history_flattens_related_job_title(self) -> None:
        candidate_id = uuid4()
        job_id = uuid4()
        row = {
            "id": uuid4(),
            "job_id": job_id,
            "current_stage": "technical_interview",
            "pipeline_status": "active_pipeline",
            "final_decision": "pending",
            "remarks": None,
            "screening_summary": "Evidence did not meet the required criteria.",
            "created_at": datetime(2026, 9, 29, tzinfo=timezone.utc),
            "jobs": {"title": "Data Engineer"},
        }
        client = FakeSupabaseClient([[row]])

        with patch.object(candidates_db, "supabase_client", client):
            history = candidates_db.get_candidate_history(candidate_id)

        self.assertEqual(history[0].job_title, "Data Engineer")
        self.assertEqual(history[0].job_id, job_id)
        self.assertEqual(
            history[0].screening_summary,
            "Evidence did not meet the required criteria.",
        )

    def test_dashboard_view_rows_are_validated(self) -> None:
        app = application_row()
        candidate = candidate_row(app["candidate_id"])
        row = {
            "application_id": app["id"],
            "candidate_id": app["candidate_id"],
            "job_id": app["job_id"],
            "full_name": candidate["full_name"],
            "email": candidate["email"],
            "phone": candidate["phone"],
            "linkedin_url": candidate["linkedin_url"],
            "job_title": "Data Engineer",
            "current_stage": "sync_evaluation",
            "agent_decision": None,
            "screening_summary": None,
            "hr_override_status": None,
            "examiner": "agent",
            "pipeline_status": "active_pipeline",
            "final_decision": "pending",
            "remarks": None,
            "application_created_at": app["created_at"],
        }
        client = FakeSupabaseClient([[row]])

        with patch.object(candidates_db, "supabase_client", client):
            records = candidates_db.list_passed_dashboard()

        self.assertIsInstance(records[0], ApplicationDashboardRecord)
        self.assertEqual(records[0].job_title, "Data Engineer")
        self.assertIn(("table", "hr_passed_candidates_dashboard"), client.events)

    def test_failed_dashboard_reads_failed_view(self) -> None:
        app = application_row()
        candidate = candidate_row(app["candidate_id"])
        row = {
            "application_id": app["id"],
            "candidate_id": app["candidate_id"],
            "job_id": app["job_id"],
            "full_name": candidate["full_name"],
            "email": candidate["email"],
            "phone": candidate["phone"],
            "linkedin_url": candidate["linkedin_url"],
            "job_title": "Data Engineer",
            "current_stage": "sync_evaluation",
            "agent_decision": "fail",
            "screening_summary": "Insufficient evidence for the required skill.",
            "hr_override_status": None,
            "examiner": "agent",
            "pipeline_status": "failed_at_sync",
            "final_decision": "fail",
            "remarks": None,
            "application_created_at": app["created_at"],
        }
        client = FakeSupabaseClient([[row]])

        with patch.object(candidates_db, "supabase_client", client):
            records = candidates_db.list_failed_dashboard(job_id=app["job_id"])

        self.assertEqual(records[0].agent_decision.value, "fail")
        self.assertIn(("table", "hr_failed_candidates_dashboard"), client.events)

    def test_hr_override_updates_only_sync_failed_application(self) -> None:
        row = application_row()
        row.update(
            {
                "hr_override_status": "pass",
                "pipeline_status": "active_pipeline",
                "final_decision": "pending",
                "examiner": "hr-user",
            }
        )
        client = FakeSupabaseClient([[row]])

        with patch.object(candidates_db, "supabase_client", client):
            result = candidates_db.apply_hr_pass_override(
                row["id"], hr_username=" hr-user "
            )

        self.assertEqual(result.pipeline_status.value, "active_pipeline")
        self.assertIn(
            ("applications", "eq", "pipeline_status", "failed_at_sync"),
            client.events,
        )


class InterviewCrudTests(TestCase):
    def test_list_interview_rounds_orders_by_sequence(self) -> None:
        application_id = uuid4()
        row = interview_row(application_id, sequence_order=2)
        client = FakeSupabaseClient([[row]])

        with patch.object(interviews_db, "supabase_client", client):
            rounds = interviews_db.list_interview_rounds(application_id)

        self.assertEqual(rounds[0].sequence_order, 2)
        self.assertIn(("interviews", "order", "sequence_order", False), client.events)

    def test_schedule_assigns_next_round_number_server_side(self) -> None:
        application_id = uuid4()
        row = interview_row(application_id, sequence_order=3)
        client = FakeSupabaseClient([[{"sequence_order": 2}], [row]])
        schedule = InterviewScheduleRequest(
            scheduled_at=datetime(2026, 10, 1, 15, tzinfo=timezone.utc)
        )

        with patch.object(interviews_db, "supabase_client", client):
            interview = interviews_db.schedule_interview_round(application_id, schedule)

        self.assertEqual(interview.sequence_order, 3)
        insert_event = next(event for event in client.events if event[1] == "insert")
        self.assertEqual(insert_event[2]["sequence_order"], 3)
        self.assertNotIn("sequence_order", schedule.model_dump())

    def test_update_round_persists_only_supplied_fields(self) -> None:
        application_id = uuid4()
        row = interview_row(application_id)
        row["feedback"] = "Clear explanation."
        client = FakeSupabaseClient([[row]])
        interview_id = row["id"]
        update = InterviewRoundUpdate(feedback="Clear explanation.")

        with patch.object(interviews_db, "supabase_client", client):
            interview = interviews_db.update_interview_round(interview_id, update)

        update_event = next(event for event in client.events if event[1] == "update")
        self.assertEqual(update_event[2], {"feedback": "Clear explanation."})
        self.assertEqual(interview.feedback, "Clear explanation.")

    def test_delete_round_removes_and_reindexes_sequence(self) -> None:
        application_id = uuid4()
        row = interview_row(application_id, sequence_order=2)
        row["local_audio_path"] = None
        client = FakeSupabaseClient([[row], [{"id": row["id"]}], []])

        with patch.object(interviews_db, "supabase_client", client):
            deleted = interviews_db.delete_interview_round(row["id"])

        self.assertTrue(deleted)
        self.assertIn(("interviews", "delete"), client.events)

    def test_recording_reference_requires_verified_file(self) -> None:
        result = InterviewRecordingResult(
            interview_id=uuid4(),
            sequence_order=1,
            interview_date=date(2026, 10, 1),
            local_audio_path=(
                "./backend/recordings/Data_Engineer/Alex_Doe/20261001/"
                "technical_interview_1.mp3"
            ),
            recording_verified=False,
        )

        with self.assertRaises(ValueError):
            interviews_db.save_recording_reference(result)

    def test_verified_recording_reference_is_persisted(self) -> None:
        interview_id = uuid4()
        row = interview_row(uuid4(), sequence_order=1)
        row["id"] = interview_id
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            recording_path = (
                root
                / "Data_Engineer"
                / "Alex_Doe"
                / "20261001"
                / "technical_interview_1.mp3"
            )
            recording_path.parent.mkdir(parents=True)
            recording_path.write_bytes(b"verified bytes")
            result = InterviewRecordingResult(
                interview_id=interview_id,
                sequence_order=1,
                interview_date=date(2026, 10, 1),
                local_audio_path=str(recording_path),
                recording_verified=True,
            )
            row["interview_date"] = "2026-10-01"
            row["local_audio_path"] = str(recording_path)
            client = FakeSupabaseClient([[{"sequence_order": 1}], [row]])

            with patch.object(interviews_db, "supabase_client", client):
                saved = interviews_db.save_recording_reference(
                    result,
                    recordings_root=root,
                )

        self.assertEqual(saved.local_audio_path, str(recording_path))
        update_event = next(event for event in client.events if event[1] == "update")
        self.assertEqual(update_event[2]["interview_date"], "2026-10-01")

    def test_database_errors_are_wrapped_without_record_contents(self) -> None:
        client = FakeSupabaseClient([RuntimeError("candidate PII in remote error")])
        payload = JobCreate(
            title="Data Engineer",
            tech_stack="Python",
            seniority="Senior",
        )

        with patch.object(jobs_db, "supabase_client", client):
            with self.assertRaises(DatabaseOperationError) as raised:
                jobs_db.create_job(payload)

        self.assertNotIn("candidate PII", str(raised.exception))

def user_row() -> dict[str, object]:
    # Mirrors a real `select("*")` row from public.users, which always
    # includes the password_hash column.
    return {
        "id": uuid4(),
        "email": "admin@recruitment-v2.com",
        "password_hash": "$2b$12$fakehashfortests",
        "full_name": "HR Admin",
        "role": "hr",
        "is_active": True,
        "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
    }


class UserCrudTests(TestCase):
    def test_row_to_user_strips_password_hash(self) -> None:
        from app.database.crud import users_db

        user = users_db._row_to_user(user_row())

        self.assertEqual(user.email, "admin@recruitment-v2.com")
        self.assertFalse(hasattr(user, "password_hash"))

    def test_get_user_password_hash_by_email_returns_hash_separately(self) -> None:
        from app.database.crud import users_db

        row = user_row()
        client = FakeSupabaseClient([[row]])

        with patch.object(users_db, "supabase_client", client):
            result = users_db.get_user_password_hash_by_email("admin@recruitment-v2.com")

        assert result is not None
        user, password_hash = result
        self.assertEqual(user.id, row["id"])
        self.assertEqual(password_hash, row["password_hash"])
        self.assertFalse(hasattr(user, "password_hash"))

    def test_create_user_strips_password_hash_from_insert_response(self) -> None:
        from app.database.crud import users_db
        from app.schemas.auth_schema import UserCreate

        row = user_row()
        client = FakeSupabaseClient([[row]])
        payload = UserCreate(
            email="admin@recruitment-v2.com",
            password="supersecret123",
            full_name="HR Admin",
        )

        with patch.object(users_db, "supabase_client", client):
            user = users_db.create_user(payload, password_hash="$2b$12$fakehashfortests")

        self.assertEqual(user.email, "admin@recruitment-v2.com")
        self.assertFalse(hasattr(user, "password_hash"))
