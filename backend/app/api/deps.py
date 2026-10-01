"""Authentication and role-based access control dependencies."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database.crud import users_db
from app.schemas.auth_schema import UserRead, UserRole
from app.services.auth_service import (
    AuthConfigurationError,
    InvalidTokenError,
    decode_access_token,
    get_user_from_token_subject,
)
from app.utils.logging import get_logger


_logger = get_logger("app.auth")

_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> UserRead:
    """Resolve the JWT bearer token to an active user. Raises 401 on failure."""
    if credentials is None or not credentials.credentials:
        raise _unauthorized()
    try:
        claims = decode_access_token(credentials.credentials)
    except AuthConfigurationError:
        _logger.error("auth attempted without JWT configuration")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication is not configured",
        )
    except InvalidTokenError:
        raise _unauthorized("invalid or expired token")

    user = get_user_from_token_subject(str(claims.get("sub")))
    if user is None:
        raise _unauthorized("invalid or expired token")
    return user


def require_roles(*roles: UserRole):
    """Dependency factory enforcing that the current user holds one of the roles.

    Usage: ``dependencies=[Depends(require_roles(UserRole.hr))]``.
    """
    allowed = set(roles)

    def _role_checker(current_user: UserRead = Depends(get_current_user)) -> UserRead:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient permissions",
            )
        return current_user

    return _role_checker


# Convenience dependency aliases matching the spec's access tiers.
require_hr = require_roles(UserRole.hr)
require_ceo = require_roles(UserRole.ceo)
require_any_role = require_roles(UserRole.hr, UserRole.interviewer, UserRole.ceo)
