"""Create the first HR admin user from ADMIN_EMAIL / ADMIN_PASSWORD.

Run from the backend directory::

    ADMIN_EMAIL=hr@example.com ADMIN_PASSWORD='change-me' python -m scripts.seed_admin

Idempotent: exits 0 without changes when a user with that email already exists.
Writes an audit log entry on creation.
"""

import sys

from app.config import settings
from app.database.crud import users_db
from app.database.crud.errors import DatabaseOperationError
from app.schemas.auth_schema import UserCreate, UserRole
from app.services import audit
from app.services.auth_service import hash_password
from app.services.supabase_service import SupabaseConfigurationError
from app.utils.logging import configure_logging, get_logger


configure_logging()
_logger = get_logger("app.seed_admin")


def main() -> int:
    email = settings.admin_email
    password = settings.admin_password.get_secret_value() if settings.admin_password else None
    if not email or not password:
        print("ADMIN_EMAIL and ADMIN_PASSWORD must be set", file=sys.stderr)
        return 2

    try:
        existing = users_db.get_user_by_email(email)
    except (SupabaseConfigurationError, DatabaseOperationError) as error:
        print(f"database unavailable: {error}", file=sys.stderr)
        return 1

    if existing is not None:
        print(f"user already exists: {existing.email} (role={existing.role.value})")
        return 0

    created = users_db.create_user(
        UserCreate(email=email, password=password, full_name="HR Admin", role=UserRole.hr),
        password_hash=hash_password(password),
    )
    _logger.info("admin user created", user_id=str(created.id), email=created.email)
    audit.record_audit(
        action="user_created",
        entity="user",
        entity_id=created.id,
        actor=created,
        metadata={"role": created.role.value, "seeded": True},
    )
    print(f"created HR admin: {created.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
