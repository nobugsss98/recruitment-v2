from pathlib import Path
from uuid import UUID

from app.database.crud.errors import DatabaseOperationError, execute_query
from app.schemas.interviews_schema import (
    InterviewRecordingResult,
    InterviewRoundRead,
    InterviewRoundUpdate,
    InterviewScheduleRequest,
)
from app.services.supabase_service import supabase_client
from app.utils.file_handler import verify_recording


def list_interview_rounds(application_id: UUID) -> list[InterviewRoundRead]:
    rows = execute_query(
        supabase_client.table("interviews")
        .select("*")
        .eq("application_id", str(application_id))
        .order("sequence_order"),
        operation="list interview rounds",
    )
    return [InterviewRoundRead.model_validate(row) for row in rows]


def get_interview_round(interview_id: UUID) -> InterviewRoundRead | None:
    rows = execute_query(
        supabase_client.table("interviews")
        .select("*")
        .eq("id", str(interview_id))
        .limit(1),
        operation="get interview round",
    )
    return InterviewRoundRead.model_validate(rows[0]) if rows else None


def schedule_interview_round(
    application_id: UUID,
    schedule: InterviewScheduleRequest,
) -> InterviewRoundRead:
    existing = execute_query(
        supabase_client.table("interviews")
        .select("sequence_order")
        .eq("application_id", str(application_id))
        .order("sequence_order", desc=True)
        .limit(1),
        operation="get latest interview sequence",
    )
    next_sequence = int(existing[0]["sequence_order"]) + 1 if existing else 1
    values = {
        "application_id": str(application_id),
        "sequence_order": next_sequence,
        "scheduled_at": schedule.scheduled_at.isoformat(),
    }
    rows = execute_query(
        supabase_client.table("interviews").insert(values).select("*"),
        operation="schedule interview round",
    )
    if not rows:
        raise DatabaseOperationError("schedule interview returned no row")
    return InterviewRoundRead.model_validate(rows[0])


def update_interview_round(
    interview_id: UUID,
    update: InterviewRoundUpdate,
) -> InterviewRoundRead | None:
    values = update.model_dump(mode="json", exclude_unset=True)
    rows = execute_query(
        supabase_client.table("interviews")
        .update(values)
        .eq("id", str(interview_id))
        .select("*"),
        operation="update interview round",
    )
    return InterviewRoundRead.model_validate(rows[0]) if rows else None


def save_recording_reference(
    result: InterviewRecordingResult,
    *,
    recordings_root: Path | str | None = None,
) -> InterviewRoundRead | None:
    expected_name = f"technical_interview_{result.sequence_order}.mp3"
    if not result.recording_verified or Path(result.local_audio_path).name != expected_name:
        raise ValueError("recording reference is not verified for this interview round")
    if not verify_recording(result.local_audio_path, recordings_root=recordings_root):
        raise ValueError("recording file is missing, empty, or outside RECORDINGS_DIR")

    existing = execute_query(
        supabase_client.table("interviews")
        .select("sequence_order")
        .eq("id", str(result.interview_id))
        .limit(1),
        operation="verify interview round for recording",
    )
    if not existing:
        return None
    if existing[0]["sequence_order"] != result.sequence_order:
        raise ValueError("recording sequence does not match the interview record")

    updated = execute_query(
        supabase_client.table("interviews")
        .update(
            {
                "interview_date": result.interview_date.isoformat(),
                "local_audio_path": result.local_audio_path,
            }
        )
        .eq("id", str(result.interview_id))
        .eq("sequence_order", result.sequence_order)
        .select("*"),
        operation="save verified recording reference",
    )
    return InterviewRoundRead.model_validate(updated[0]) if updated else None


def delete_interview_round(interview_id: UUID) -> bool:
    current = execute_query(
        supabase_client.table("interviews")
        .select("*")
        .eq("id", str(interview_id))
        .limit(1),
        operation="load interview round for deletion",
    )
    if not current:
        return False

    interview = InterviewRoundRead.model_validate(current[0])
    if interview.local_audio_path:
        try:
            audio_path = Path(interview.local_audio_path)
            if audio_path.exists() and audio_path.is_file():
                audio_path.unlink()
        except OSError:
            pass

    deleted = execute_query(
        supabase_client.table("interviews")
        .delete()
        .eq("id", str(interview_id))
        .select("id"),
        operation="delete interview round",
    )
    if not deleted:
        return False

    remaining = execute_query(
        supabase_client.table("interviews")
        .select("*")
        .eq("application_id", str(interview.application_id))
        .order("sequence_order"),
        operation="fetch remaining interview rounds for reindexing",
    )
    for index, row in enumerate(remaining, start=1):
        if row["sequence_order"] == index:
            continue
        execute_query(
            supabase_client.table("interviews")
            .update({"sequence_order": index})
            .eq("id", str(row["id"]))
            .select("*"),
            operation="reindex interview round sequence",
        )

    return True