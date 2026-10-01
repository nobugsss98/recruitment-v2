import os
from datetime import date
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from app.config import REPOSITORY_ROOT, Settings
from app.utils.anonymizer import anonymize_applicant_text
from app.utils.file_handler import (
    build_recording_path,
    save_recording,
    sanitize_path_segment,
    verify_recording,
)


class RecordingPathTests(TestCase):
    def test_relative_recordings_dir_resolves_from_repository_root(self) -> None:
        with patch.dict(os.environ, {"RECORDINGS_DIR": "./custom-recordings"}):
            settings = Settings(_env_file=None)

        self.assertEqual(
            settings.recordings_dir,
            (REPOSITORY_ROOT / "custom-recordings").resolve(),
        )

    def test_path_uses_sanitized_segments_date_and_sequence(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = build_recording_path(
                job_title="Data/Engineering",
                candidate_name="Alex Doe",
                interview_date=date(2026, 10, 1),
                sequence_order=2,
                recordings_root=root,
            )

        self.assertEqual(
            path,
            root
            / "Data_Engineering"
            / "Alex_Doe"
            / "20261001"
            / "technical_interview_2.mp3",
        )

    def test_path_rejects_invalid_sequence_and_empty_segments(self) -> None:
        with self.assertRaises(ValueError):
            build_recording_path(
                job_title="Engineer",
                candidate_name="Alex Doe",
                interview_date=date(2026, 10, 1),
                sequence_order=0,
                recordings_root=Path("recordings"),
            )

        with self.assertRaises(ValueError):
            sanitize_path_segment("../../")

    def test_recording_save_verifies_file_and_never_overwrites(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            recording_path = save_recording(
                BytesIO(b"unparsed interview recording bytes"),
                job_title="Data Engineer",
                candidate_name="Alex Doe",
                interview_date=date(2026, 10, 1),
                sequence_order=1,
                recordings_root=root,
            )

            self.assertTrue(verify_recording(recording_path, recordings_root=root))
            self.assertEqual(
                recording_path.read_bytes(), b"unparsed interview recording bytes"
            )

            with self.assertRaises(FileExistsError):
                save_recording(
                    BytesIO(b"replacement must not be written"),
                    job_title="Data Engineer",
                    candidate_name="Alex Doe",
                    interview_date=date(2026, 10, 1),
                    sequence_order=1,
                    recordings_root=root,
                )

            self.assertEqual(
                recording_path.read_bytes(), b"unparsed interview recording bytes"
            )

    def test_empty_recordings_are_removed_and_not_verified(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = build_recording_path(
                job_title="Data Engineer",
                candidate_name="Alex Doe",
                interview_date=date(2026, 10, 1),
                sequence_order=1,
                recordings_root=root,
            )

            with self.assertRaises(ValueError):
                save_recording(
                    BytesIO(b""),
                    job_title="Data Engineer",
                    candidate_name="Alex Doe",
                    interview_date=date(2026, 10, 1),
                    sequence_order=1,
                    recordings_root=root,
                )

            self.assertFalse(path.exists())
            self.assertFalse(verify_recording(path, recordings_root=root))

    def test_verification_rejects_paths_outside_recordings_root(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "recordings"
            outside = Path(temporary_directory) / "outside.mp3"
            outside.write_bytes(b"not in recordings root")

            self.assertFalse(verify_recording(outside, recordings_root=root))


class AnonymizerTests(TestCase):
    def test_replaces_supplied_demographics_and_preserves_experience(self) -> None:
        text = (
            "Alex Doe is 34 years old. Age: 34 | Gender: Female | "
            "Experience: 8 years in data engineering."
        )

        anonymized = anonymize_applicant_text(
            text,
            full_name="Alex Doe",
            age=34,
            gender="Female",
        )

        self.assertNotIn("Alex Doe", anonymized)
        self.assertNotIn("34", anonymized)
        self.assertNotIn("Female", anonymized)
        self.assertIn("[NAME]", anonymized)
        self.assertIn("[AGE]", anonymized)
        self.assertIn("[GENDER]", anonymized)
        self.assertIn("Experience: 8 years in data engineering.", anonymized)

    def test_anonymizer_requires_text_and_candidate_name(self) -> None:
        with self.assertRaises(ValueError):
            anonymize_applicant_text("Resume text", full_name="  ")

    def test_name_matching_is_case_insensitive_with_flexible_whitespace(self) -> None:
        anonymized = anonymize_applicant_text(
            "ALEX    DOE led a team.",
            full_name="Alex Doe",
        )

        self.assertEqual(anonymized, "[NAME] led a team.")
