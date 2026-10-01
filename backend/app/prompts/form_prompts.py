import json

from app.schemas.google_forms_schema import GoogleFormQuestionSet
from app.schemas.jobs_schema import JobCreate


FORM_QUESTION_SYSTEM_PROMPT = """
Create a concise, role-specific, job-specific set of application questions from the supplied
validated job criteria. Do not reuse a fixed question list: tailor each
question to the role's actual responsibilities, required skills, and seniority.
Ask about evidence of relevant experience and practical work, not protected or
unrelated personal characteristics. Do not ask for information already
collected by the template's résumé-upload question, and do not create a résumé
upload question because the template already contains it.

Return between 2 and 8 distinct, clear questions. Use short_text or paragraph
for open responses, and use multiple_choice or checkbox only when the supplied
criteria support meaningful options. Choice questions must have at least two
distinct options. Mark questions required unless an answer is reasonably
optional. Return only data matching the requested GoogleFormQuestionSet schema;
do not include commentary, extra fields, or hidden reasoning.
""".strip()


def build_form_questions_user_prompt(job: JobCreate) -> str:
    if not isinstance(job, JobCreate):
        raise TypeError("job must be a validated JobCreate model")
    return json.dumps(
        job.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )


FORM_QUESTION_RESPONSE_SCHEMA = GoogleFormQuestionSet