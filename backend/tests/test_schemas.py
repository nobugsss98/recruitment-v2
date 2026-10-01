from datetime import date, datetime, timezone
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

from pydantic import ValidationError

from app.schemas.candidates_schema import (
    ApplicationScreeningResult,
    CandidateCreate,
    CandidateIdentityLookup,
    FinalDecision,
    HROverrideRequest,
    PipelineStatus,
    ScreeningDecision,
)
from app.schemas.interviews_schema import (
    InterviewRecordingResult,
    InterviewRoundRead,
    InterviewRoundUpdate,
    InterviewScheduleRequest,
    InterviewStatus,
)
from app.schemas.jobs_schema import JobCreate, JobPatch, JobStatus


class JobSchemaTests(TestCase):
    def test_job_create_strips_whitespace_and_accepts_valid_compensation(self) -> None:
        job = JobCreate(
            title="  Data Engineer  ",
            tech_stack="  Python, Postgres  ",
            seniority="  Senior  ",
            compensation_min=Decimal("100000.00"),
            compensation_max=Decimal("150000.00"),
        )

        self.assertEqual(job.title, "Data Engineer")
        self.assertEqual(job.tech_stack, "Python, Postgres")
        self.assertEqual(job.seniority, "Senior")

    def test_job_create_rejects_invalid_compensation_range(self) -> None:
        with self.assertRaises(ValidationError):
            JobCreate(
                title="Data Engineer",
                tech_stack="Python",
                seniority="Senior",
                compensation_min=Decimal("150000"),
                compensation_max=Decimal("100000"),
            )

    def test_job_create_rejects_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            JobCreate(
                title="Data Engineer",
                tech_stack="Python",
                seniority="Senior",
                unexpected="not accepted",
            )

    def test_job_patch_requires_at_least_one_field(self) -> None:
        with self.assertRaises(ValidationError):
            JobPatch()

    def test_job_patch_accepts_partial_update(self) -> None:
        patch = JobPatch(status=JobStatus.posted)
        self.assertEqual(patch.status, JobStatus.posted)


class CandidateAndApplicationSchemaTests(TestCase):
    def test_candidate_create_validates_email(self) -> None:
        candidate = CandidateCreate(
            full_name="Alex Doe",
            email="alex@example.com",
        )
        self.assertEqual(str(candidate.email), "alex@example.com")

    def test_candidate_create_rejects_invalid_email(self) -> None:
        with self.assertRaises(ValidationError):
            CandidateCreate(full_name="Alex Doe", email="not-an-email")

    def test_identity_lookup_accepts_one_matching_key(self) -> None:
        lookup = CandidateIdentityLookup(phone="+15551234567")
        self.assertEqual(lookup.phone, "+15551234567")

    def test_identity_lookup_requires_a_matching_key(self) -> None:
        with self.assertRaises(ValidationError):
            CandidateIdentityLookup()

    def test_screening_result_rejects_private_reasoning_field(self) -> None:
        with self.assertRaises(ValidationError):
            ApplicationScreeningResult(
                agent_decision=ScreeningDecision.failed,
                screening_summary="Missing required experience.",
                chain_of_thought="private reasoning",
            )

    def test_hr_override_requires_human_username(self) -> None:
        with self.assertRaises(ValidationError):
            HROverrideRequest(hr_username="   ")

    def test_pipeline_status_includes_database_default(self) -> None:
        self.assertEqual(PipelineStatus.failed_at_sync.value, "failed_at_sync")
        self.assertEqual(FinalDecision.pending.value, "pending")


class InterviewSchemaTests(TestCase):
    def test_schedule_requires_timezone_aware_datetime(self) -> None:
        scheduled = InterviewScheduleRequest(
            scheduled_at=datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(scheduled.scheduled_at.utcoffset().total_seconds(), 0)

        with self.assertRaises(ValidationError):
            InterviewScheduleRequest(scheduled_at=datetime(2026, 10, 1, 15, 0))

    def test_schedule_does_not_accept_client_assigned_round_number(self) -> None:
        with self.assertRaises(ValidationError):
            InterviewScheduleRequest(
                scheduled_at=datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc),
                sequence_order=4,
            )

    def test_interview_update_requires_at_least_one_change(self) -> None:
        with self.assertRaises(ValidationError):
            InterviewRoundUpdate()

        update = InterviewRoundUpdate(feedback="Strong debugging approach.")
        self.assertEqual(update.feedback, "Strong debugging approach.")

    def test_interview_response_requires_positive_sequence(self) -> None:
        with self.assertRaises(ValidationError):
            InterviewRoundRead(
                id=uuid4(),
                application_id=uuid4(),
                sequence_order=0,
                scheduled_at=None,
                interview_date=None,
                local_audio_path=None,
                feedback=None,
                status=InterviewStatus.pending,
                created_at=datetime(2026, 9, 29, tzinfo=timezone.utc),
            )

    def test_recording_result_reports_round_specific_local_path(self) -> None:
        result = InterviewRecordingResult(
            interview_id=uuid4(),
            sequence_order=2,
            interview_date=date(2026, 10, 1),
            local_audio_path=(
                "./backend/recordings/Data_Engineer/Alex_Doe/20261001/"
                "technical_interview_2.mp3"
            ),
            recording_verified=True,
        )
        self.assertTrue(result.recording_verified)
        self.assertIn("technical_interview_2.mp3", result.local_audio_path)
