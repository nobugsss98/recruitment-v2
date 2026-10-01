import re
import shutil
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import BinaryIO

from app.config import settings


_INVALID_SEGMENT_CHARACTERS = re.compile(r"[^\w -]+", re.UNICODE)
_REPEATED_SEPARATORS = re.compile(r"[\s_-]+")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def sanitize_path_segment(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("path segment must be a string")

    normalized = unicodedata.normalize("NFKC", value).strip()
    safe = _INVALID_SEGMENT_CHARACTERS.sub("_", normalized)
    safe = _REPEATED_SEPARATORS.sub("_", safe).strip("._- ")[:120].strip("._- ")

    if not safe:
        raise ValueError("path segment must contain at least one safe character")
    if safe.upper() in _WINDOWS_RESERVED_NAMES:
        safe = f"_{safe}"

    return safe


def _recordings_root(recordings_root: Path | str | None) -> Path:
    configured_root = settings.recordings_dir if recordings_root is None else recordings_root
    return Path(configured_root).expanduser().resolve()


def build_recording_path(
    *,
    job_title: str,
    candidate_name: str,
    interview_date: date,
    sequence_order: int,
    recordings_root: Path | str | None = None,
) -> Path:
    if isinstance(interview_date, datetime) or not isinstance(interview_date, date):
        raise TypeError("interview_date must be a date, not a datetime")
    if isinstance(sequence_order, bool) or not isinstance(sequence_order, int):
        raise TypeError("sequence_order must be an integer")
    if sequence_order < 1:
        raise ValueError("sequence_order must be positive")

    root = _recordings_root(recordings_root)
    path = (
        root
        / sanitize_path_segment(job_title)
        / sanitize_path_segment(candidate_name)
        / interview_date.strftime("%Y%m%d")
        / f"technical_interview_{sequence_order}.mp3"
    ).resolve()

    if not path.is_relative_to(root):
        raise ValueError("recording path must remain inside RECORDINGS_DIR")

    return path


def verify_recording(
    path: Path | str,
    *,
    recordings_root: Path | str | None = None,
) -> bool:
    root = _recordings_root(recordings_root)
    try:
        recording = Path(path).resolve(strict=True)
        return (
            recording.is_relative_to(root)
            and recording.suffix.lower() == ".mp3"
            and recording.is_file()
            and recording.stat().st_size > 0
        )
    except (OSError, RuntimeError, ValueError):
        return False


def save_recording(
    source: BinaryIO,
    *,
    job_title: str,
    candidate_name: str,
    interview_date: date,
    sequence_order: int,
    recordings_root: Path | str | None = None,
) -> Path:
    root = _recordings_root(recordings_root)
    destination = build_recording_path(
        job_title=job_title,
        candidate_name=candidate_name,
        interview_date=interview_date,
        sequence_order=sequence_order,
        recordings_root=root,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)

    created = False
    try:
        with destination.open("xb") as target:
            created = True
            shutil.copyfileobj(source, target, length=1024 * 1024)
        if destination.stat().st_size == 0:
            raise ValueError("recording must not be empty")
        if not verify_recording(destination, recordings_root=root):
            raise OSError("saved recording failed local file verification")
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise

    return destination