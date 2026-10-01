import re


_AGE_FIELD = re.compile(r"\bage\s*[:=]\s*[^,;|.\r\n]+", re.IGNORECASE)
_GENDER_FIELD = re.compile(
    r"\b(?:gender(?:\s+identity)?|sex)\s*[:=]\s*[^,;|.\r\n]+",
    re.IGNORECASE,
)


def _replace_literal(text: str, value: str | None, replacement: str) -> str:
    if value is None or not value.strip():
        return text

    escaped = re.escape(value.strip()).replace(r"\ ", r"\s+")
    pattern = rf"(?<!\w){escaped}(?!\w)"
    return re.sub(pattern, replacement, text, flags=re.IGNORECASE)


def anonymize_applicant_text(
    text: str,
    *,
    full_name: str,
    age: int | None = None,
    gender: str | None = None,
    email: str | None = None,
) -> str:
    if not isinstance(text, str):
        raise TypeError("applicant text must be a string")
    if not isinstance(full_name, str) or not full_name.strip():
        raise ValueError("full_name must be a non-empty string")
    if age is not None and (isinstance(age, bool) or not isinstance(age, int) or age < 0):
        raise ValueError("age must be a non-negative integer or None")
    if gender is not None and not isinstance(gender, str):
        raise TypeError("gender must be a string or None")
    if email is not None and not isinstance(email, str):
        raise TypeError("email must be a string or None")

    anonymized = _AGE_FIELD.sub("[AGE]", text)
    anonymized = _GENDER_FIELD.sub("[GENDER]", anonymized)

    if age is not None:
        age_patterns = (
            rf"\b{age}\s+years?\s+old\b",
            rf"\b{age}[- ]year[- ]old\b",
            rf"\b{age}\s*yo\b",
        )
        for pattern in age_patterns:
            anonymized = re.sub(pattern, "[AGE]", anonymized, flags=re.IGNORECASE)

    anonymized = _replace_literal(anonymized, gender, "[GENDER]")
    anonymized = _replace_literal(anonymized, email, "[EMAIL]")
    anonymized = _replace_literal(anonymized, full_name, "[NAME]")
    anonymized = re.sub(r"[ \t]+", " ", anonymized)
    anonymized = re.sub(r" *\n *", "\n", anonymized)
    anonymized = re.sub(r"\n{3,}", "\n\n", anonymized)
    return anonymized.strip()