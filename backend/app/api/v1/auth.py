from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.schemas.auth_schema import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserRead,
)
from app.services import audit
from app.services.auth_service import (
    AuthConfigurationError,
    InvalidTokenError,
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_user_from_token_subject,
)
from app.utils.logging import get_logger


router = APIRouter(prefix="/auth", tags=["auth"])
_logger = get_logger("app.auth")


def _issue_tokens(user: UserRead) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user),
        refresh_token=create_refresh_token(user),
        user=user,
    )


@router.post("/login", response_model=TokenResponse)
def login_route(request: LoginRequest) -> TokenResponse:
    try:
        user = authenticate_user(request.email, request.password)
        if user is None:
            _logger.warning("login failed", email=request.email)
            audit.record_audit(
                action="login_failed",
                entity="user",
                actor_email=request.email,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid email or password",
            )
        tokens = _issue_tokens(user)
    except AuthConfigurationError:
        _logger.error("login attempted without JWT configuration")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication is not configured",
        )
    _logger.info("login succeeded", user_id=str(user.id), role=user.role.value)
    audit.record_audit(
        action="login",
        entity="user",
        entity_id=user.id,
        actor=user,
    )
    return tokens


@router.post("/refresh", response_model=TokenResponse)
def refresh_route(request: RefreshRequest) -> TokenResponse:
    try:
        claims = decode_refresh_token(request.refresh_token)
        user = get_user_from_token_subject(str(claims.get("sub")))
        if user is None:
            raise InvalidTokenError("unknown token subject")
        tokens = _issue_tokens(user)
    except AuthConfigurationError:
        _logger.error("refresh attempted without JWT configuration")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication is not configured",
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired refresh token",
        )
    _logger.info("token refreshed", user_id=str(user.id))
    return tokens


@router.get("/me", response_model=UserRead)
def me_route(current_user: UserRead = Depends(get_current_user)) -> UserRead:
    return current_user
