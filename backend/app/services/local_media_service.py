from datetime import date
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from app.schemas.interviews_schema import InterviewRecordingResult
from app.utils.file_handler import save_recording, verify_recording


class LocalMediaStorageError(RuntimeError):
    """Raised when a local interview recording cannot be stored or verified."""


def store_interview_recording(
    source: BinaryIO,
    *,
    interview_id: UUID,
    job_title: str,
    candidate_name: str,
    interview_date: date,
    sequence_order: int,
    recordings_root: Path | str | None = None,
) -> InterviewRecordingResult:
    path = save_recording(
        source,
        job_title=job_title,
        candidate_name=candidate_name,
        interview_date=interview_date,
        sequence_order=sequence_order,
        recordings_root=recordings_root,
    )
    verified = verify_recording(path, recordings_root=recordings_root)
    if not verified:
        raise LocalMediaStorageError("saved interview recording did not pass verification")

    return InterviewRecordingResult(
        interview_id=interview_id,
        sequence_order=sequence_order,
        interview_date=interview_date,
        local_audio_path=str(path),
        recording_verified=True,
    )