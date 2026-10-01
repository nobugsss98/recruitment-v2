import json

from app.schemas.jobs_schema import JobCreate


JOB_DESCRIPTION_SYSTEM_PROMPT = """
You draft clear, inclusive, professional job descriptions for human review.

Use only the validated job criteria supplied in the user payload. Do not invent
responsibilities, qualifications, benefits, company facts, location, work
arrangement, or compensation. If compensation is absent, omit compensation
language. Keep required qualifications distinct from preferred qualifications;
do not turn preferred criteria into requirements. Use the supplied title,
technology stack, and seniority accurately. Avoid discriminatory wording and
do not add age, gender, or other personal-characteristic requirements.

Return editable Markdown only, with a concise role overview and useful sections
for responsibilities, required qualifications, and preferred qualifications.
Omit a section when the supplied criteria do not support it. Do not include
prefatory commentary, claims that facts were verified, or details not present
in the criteria.
""".strip()


def build_job_description_user_prompt(job: JobCreate) -> str:
    if not isinstance(job, JobCreate):
        raise TypeError("job must be a validated JobCreate model")

    return json.dumps(
        job.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )


LINKEDIN_BLURB_SYSTEM_PROMPT = """
Write a concise, professional LinkedIn job post for human review.

Use only the supplied job criteria, approved job description, and application
form URL. Do not invent company facts, location, work arrangement, benefits,
requirements, compensation, or hiring claims. Preserve the exact application
form URL and include a clear call to apply. Return plain text only.
""".strip()


def build_linkedin_blurb_user_prompt(
    job: JobCreate,
    *,
    jd_markdown: str,
    form_url: str,
) -> str:
    if not isinstance(job, JobCreate):
        raise TypeError("job must be a validated JobCreate model")
    if not isinstance(jd_markdown, str) or not jd_markdown.strip():
        raise ValueError("jd_markdown must be a non-empty string")
    if not isinstance(form_url, str) or not form_url.strip():
        raise ValueError("form_url must be a non-empty string")

    return json.dumps(
        {
            "job": job.model_dump(mode="json"),
            "jd_markdown": jd_markdown,
            "application_form_url": form_url,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )