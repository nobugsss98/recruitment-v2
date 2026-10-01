from pathlib import Path

from pydantic import AnyHttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORDINGS_DIR = REPOSITORY_ROOT / "backend" / "recordings"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / "backend" / ".env",
        extra="ignore",
        env_ignore_empty=True,
    )

    # --- Existing integrations ---
    recordings_dir: Path = DEFAULT_RECORDINGS_DIR
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    supabase_url: AnyHttpUrl | None = None
    supabase_service_role_key: SecretStr | None = None
    google_service_account_file: Path | None = None
    google_oauth_client_file: Path | None = None
    google_oauth_token_file: Path | None = None
    google_form_template_id: str | None = None
    google_drive_folder_id: str | None = None

    # --- Auth / JWT ---
    jwt_secret_key: SecretStr | None = None
    access_token_minutes: int = 30
    refresh_token_days: int = 7

    # --- HTTP ---
    cors_origins: str = "http://localhost:5173"

    # --- First admin seed ---
    admin_email: str | None = None
    admin_password: SecretStr | None = None

    @field_validator("recordings_dir", mode="before")
    @classmethod
    def resolve_recordings_dir(cls, value: Path | str) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = REPOSITORY_ROOT / path
        return path.resolve()

    @field_validator("gemini_model")
    @classmethod
    def validate_gemini_model(cls, value: str) -> str:
        model = value.strip()
        if not model:
            raise ValueError("GEMINI_MODEL must not be empty")
        return model

    @field_validator(
        "google_service_account_file",
        "google_oauth_client_file",
        "google_oauth_token_file",
        mode="before",
    )
    @classmethod
    def resolve_google_service_account_file(cls, value: Path | str | None) -> Path | None:
        if value is None or not str(value).strip():
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = REPOSITORY_ROOT / path
        return path.resolve()

    @field_validator("google_form_template_id", "google_drive_folder_id")
    @classmethod
    def normalize_google_resource_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("access_token_minutes")
    @classmethod
    def validate_access_token_minutes(cls, value: int) -> int:
        if value < 1:
            raise ValueError("ACCESS_TOKEN_MINUTES must be at least 1")
        return value

    @field_validator("refresh_token_days")
    @classmethod
    def validate_refresh_token_days(cls, value: int) -> int:
        if value < 1:
            raise ValueError("REFRESH_TOKEN_DAYS must be at least 1")
        return value

    @field_validator("admin_email")
    @classmethod
    def normalize_admin_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
