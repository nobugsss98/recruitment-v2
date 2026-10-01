from threading import Lock
from typing import Any, Callable

from supabase import Client, create_client

from app.config import Settings, settings


class SupabaseConfigurationError(RuntimeError):
    """Raised when the first database operation lacks Supabase configuration."""


class LazySupabaseClient:
    def __init__(
        self,
        *,
        settings_provider: Callable[[], Settings] = lambda: settings,
        client_factory: Callable[[str, str], Client] = create_client,
    ) -> None:
        self._settings_provider = settings_provider
        self._client_factory = client_factory
        self._client: Any | None = None
        self._lock = Lock()

    def _get_client(self) -> Any:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    configuration = self._settings_provider()
                    project_url = configuration.supabase_url
                    service_role_key = configuration.supabase_service_role_key
                    if project_url is None or service_role_key is None:
                        raise SupabaseConfigurationError(
                            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required "
                            "for database operations"
                        )
                    try:
                        self._client = self._client_factory(
                            str(project_url), service_role_key.get_secret_value()
                        )
                    except Exception:
                        raise SupabaseConfigurationError(
                            "Supabase client initialization failed"
                        ) from None
        return self._client

    def table(self, table_name: str) -> Any:
        return self._get_client().table(table_name)


supabase_client = LazySupabaseClient()