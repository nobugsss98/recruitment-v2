from uuid import UUID

from app.database.crud.errors import DatabaseOperationError, execute_query
from app.schemas.auth_schema import UserCreate, UserRead, UserRole
from app.services.supabase_service import supabase_client


def _row_to_user(row: dict) -> UserRead:
    # The users table stores password_hash, which must never leak into the
    # public UserRead model (extra="forbid" would also raise on it).
    safe_row = {k: v for k, v in row.items() if k != "password_hash"}
    return UserRead.model_validate(safe_row)


def create_user(user: UserCreate, *, password_hash: str) -> UserRead:
    rows = execute_query(
        supabase_client.table("users")
        .insert(
            {
                "email": str(user.email).lower(),
                "password_hash": password_hash,
                "full_name": user.full_name,
                "role": user.role.value,
            }
        )
        .select("*"),
        operation="create user",
    )
    if not rows:
        raise DatabaseOperationError("create user returned no row")
    return _row_to_user(rows[0])


def get_user_by_id(user_id: UUID) -> UserRead | None:
    rows = execute_query(
        supabase_client.table("users")
        .select("*")
        .eq("id", str(user_id))
        .limit(1),
        operation="get user by id",
    )
    return _row_to_user(rows[0]) if rows else None


def get_user_by_email(email: str) -> UserRead | None:
    rows = execute_query(
        supabase_client.table("users")
        .select("*")
        .ilike("email", email.strip().lower())
        .limit(1),
        operation="get user by email",
    )
    return _row_to_user(rows[0]) if rows else None


def get_user_password_hash(user_id: UUID) -> str | None:
    rows = execute_query(
        supabase_client.table("users")
        .select("password_hash")
        .eq("id", str(user_id))
        .limit(1),
        operation="get user password hash",
    )
    if not rows:
        return None
    value = rows[0].get("password_hash")
    return value if isinstance(value, str) else None


def get_user_password_hash_by_email(email: str) -> tuple[UserRead, str] | None:
    rows = execute_query(
        supabase_client.table("users")
        .select("*")
        .ilike("email", email.strip().lower())
        .limit(1),
        operation="get user with password hash",
    )
    if not rows:
        return None
    password_hash = rows[0].get("password_hash")
    if not isinstance(password_hash, str):
        return None
    return _row_to_user(rows[0]), password_hash


def list_users(*, role: UserRole | None = None) -> list[UserRead]:
    query = supabase_client.table("users").select("*")
    if role is not None:
        query = query.eq("role", role.value)
    rows = execute_query(
        query.order("created_at", desc=True),
        operation="list users",
    )
    return [_row_to_user(row) for row in rows]


def set_user_active(user_id: UUID, *, is_active: bool) -> UserRead | None:
    rows = execute_query(
        supabase_client.table("users")
        .update({"is_active": is_active})
        .eq("id", str(user_id))
        .select("*"),
        operation="set user active flag",
    )
    return _row_to_user(rows[0]) if rows else None
