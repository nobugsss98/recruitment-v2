from app.database.crud.errors import execute_query
from app.schemas.audit_schema import AuditLogCreate, AuditLogRead
from app.services.supabase_service import supabase_client


def insert_audit_log(entry: AuditLogCreate) -> AuditLogRead | None:
    rows = execute_query(
        supabase_client.table("audit_logs")
        .insert(entry.model_dump(mode="json"))
        .select("*"),
        operation="insert audit log",
    )
    return AuditLogRead.model_validate(rows[0]) if rows else None
