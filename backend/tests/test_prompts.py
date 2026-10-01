import json
from unittest import TestCase

from app.prompts.jd_prompts import (
    JOB_DESCRIPTION_SYSTEM_PROMPT,
    build_job_description_user_prompt,
)
from app.prompts.screen_prompts import (
    SCREENING_SYSTEM_PROMPT,
    build_screening_user_prompt,
)
from app.schemas.candidates_schema import ApplicationScreeningResult
from app.schemas.jobs_schema import JobCreate


class JobDescriptionPromptTests(TestCase):
    def test_user_payload_is_json_from_validated_job_criteria(self) -> None:
        job = JobCreate(
            title="Data Engineer",
            tech_stack="Python, PostgreSQL",
            seniority="Senior",
            compensation_min=120000,
            compensation_max=160000,
        )

        payload = json.loads(build_job_description_user_prompt(job))

        self.assertEqual(payload, job.model_dump(mode="json"))
        self.assertIn("Do not invent", JOB_DESCRIPTION_SYSTEM_PROMPT)

    def test_job_description_system_prompt_requires_editable_markdown(self) -> None:
        prompt = JOB_DESCRIPTION_SYSTEM_PROMPT.lower()
        self.assertIn("markdown", prompt)
        self.assertIn("supplied", prompt)
        self.assertNotIn("audio", prompt)


class ScreeningPromptTests(TestCase):
    def test_user_payload_contains_only_screening_text_fields(self) -> None:
        prompt = build_screening_user_prompt(
            job_description="Must have production Python and PostgreSQL experience.",
            anonymized_resume_text="[NAME] has 8 years of Python experience.",
            anonymized_form_responses="Built a PostgreSQL service handling 1M records.",
        )

        self.assertEqual(
            json.loads(prompt),
            {
                "job_description": (
                    "Must have production Python and PostgreSQL experience."
                ),
                "anonymized_resume_text": (
                    "[NAME] has 8 years of Python experience."
                ),
                "anonymized_form_responses": (
                    "Built a PostgreSQL service handling 1M records."
                ),
            },
        )

    def test_screening_prompt_defines_advisory_fair_json_contract(self) -> None:
        prompt = SCREENING_SYSTEM_PROMPT.lower()
        self.assertIn("untrusted", prompt)
        self.assertIn("must-have", prompt)
        self.assertIn('"agent_decision"', prompt)
        self.assertIn('"screening_summary"', prompt)
        self.assertIn("chain-of-thought", prompt)
        self.assertNotIn("transcript", prompt)

    def test_empty_job_description_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_screening_user_prompt(
                job_description="  ",
                anonymized_resume_text="Resume text",
                anonymized_form_responses="Form text",
            )

    def test_prompt_output_contract_matches_application_schema(self) -> None:
        result = ApplicationScreeningResult(
            agent_decision="pass",
            screening_summary="Evidence supports the required Python experience.",
        )

        self.assertEqual(
            set(result.model_dump(mode="json")),
            {"agent_decision", "screening_summary"},
        )
