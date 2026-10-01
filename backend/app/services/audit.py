"""Best-effort audit trail writer.

Audit writes must never break the primary business flow: failures are logged
and swallowed so the user-facing operation still completes.
"""

from uuid import UUID

from app.database.crud import audit_db
from app.schemas.audit_schema import AuditLogCreate
from app.schemas.auth_schema import UserRead
from app.utils.logging import get_logger


_logger = get_logger("app.audit")


def record_audit(
    *,
    action: str,
    entity: str,
    entity_id: str | UUID | None = None,
    actor: UserRead | None = None,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    resolved_actor_id = actor.id if actor is not None else actor_id
    resolved_actor_email = actor.email if actor is not None else actor_email
    try:
        audit_db.insert_audit_log(
            AuditLogCreate(
                actor_id=resolved_actor_id,
                actor_email=resolved_actor_email,
                action=action,
                entity=entity,
                entity_id=str(entity_id) if entity_id is not None else None,
                metadata=metadata or {},
            )
        )
    except Exception as error:
        _logger.warning(
            "audit write failed",
            action=action,
            entity=entity,
            error=type(error).__name__,
        )
