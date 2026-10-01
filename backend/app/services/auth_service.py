"""Authentication helpers: password hashing and JWT issuance/validation."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
from jose import JWTError, jwt
from pydantic import SecretStr

from app.config import settings
from app.database.crud import users_db
from app.schemas.auth_schema import UserRead


_JWT_ALGORITHM = "HS256"
_ACCESS_TOKEN_TYPE = "access"
_REFRESH_TOKEN_TYPE = "refresh"


class AuthConfigurationError(RuntimeError):
    """Raised when JWT settings are missing."""


class InvalidTokenError(ValueError):
    """Raised when a JWT is expired, malformed, or of the wrong type."""


def hash_password(plain_password: str) -> str:
    if not isinstance(plain_password, str) or not plain_password:
        raise ValueError("password must be a non-empty string")
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    if not isinstance(plain_password, str) or not isinstance(password_hash, str):
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def _jwt_secret() -> str:
    secret = settings.jwt_secret_key
    if isinstance(secret, SecretStr):
        secret = secret.get_secret_value()
    if not isinstance(secret, str) or not secret.strip():
        raise AuthConfigurationError("JWT_SECRET_KEY is required for authentication")
    return secret.strip()


def _build_token(user: UserRead, *, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_JWT_ALGORITHM)


def create_access_token(user: UserRead) -> str:
    return _build_token(
        user,
        token_type=_ACCESS_TOKEN_TYPE,
        expires_delta=timedelta(minutes=settings.access_token_minutes),
    )


def create_refresh_token(user: UserRead) -> str:
    return _build_token(
        user,
        token_type=_REFRESH_TOKEN_TYPE,
        expires_delta=timedelta(days=settings.refresh_token_days),
    )


def decode_token(token: str, *, expected_type: str) -> dict:
    """Decode a JWT and return its claims. Raises InvalidTokenError on failure."""
    try:
        claims = jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALGORITHM])
    except JWTError as error:
        raise InvalidTokenError("token is invalid or expired") from error
    if not isinstance(claims, dict) or claims.get("type") != expected_type:
        raise InvalidTokenError("token type mismatch")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise InvalidTokenError("token is missing a subject")
    return claims


def decode_access_token(token: str) -> dict:
    return decode_token(token, expected_type=_ACCESS_TOKEN_TYPE)


def decode_refresh_token(token: str) -> dict:
    return decode_token(token, expected_type=_REFRESH_TOKEN_TYPE)


def authenticate_user(email: str, password: str) -> UserRead | None:
    """Return the active user when credentials are valid, else None.

    Never raises for bad credentials; callers log only success/failure.
    """
    if not email or not password:
        return None
    record = users_db.get_user_password_hash_by_email(email)
    if record is None:
        # Run a dummy verification to keep timing roughly constant.
        verify_password(password, hash_password("dummy"))
        return None
    user, password_hash = record
    if not user.is_active:
        return None
    if not verify_password(password, password_hash):
        return None
    return user


def get_user_from_token_subject(subject: str) -> UserRead | None:
    try:
        user_id = UUID(subject)
    except (ValueError, TypeError, AttributeError):
        return None
    user = users_db.get_user_by_id(user_id)
    if user is None or not user.is_active:
        return None
    return user
