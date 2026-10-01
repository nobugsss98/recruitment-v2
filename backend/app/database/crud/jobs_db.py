from uuid import UUID

from app.database.crud.errors import DatabaseOperationError, execute_query
from app.schemas.jobs_schema import JobCreate, JobPatch, JobRead, JobStatus
from app.services.supabase_service import supabase_client


def create_job(job: JobCreate) -> JobRead:
    rows = execute_query(
        supabase_client.table("jobs")
        .insert(job.model_dump(mode="json"))
        .select("*"),
        operation="create job",
    )
    if not rows:
        raise DatabaseOperationError("create job returned no row")
    return JobRead.model_validate(rows[0])


def get_job(job_id: UUID) -> JobRead | None:
    rows = execute_query(
        supabase_client.table("jobs")
        .select("*")
        .eq("id", str(job_id))
        .limit(1),
        operation="get job",
    )
    return JobRead.model_validate(rows[0]) if rows else None


def list_jobs(*, status: JobStatus | None = None) -> list[JobRead]:
    query = supabase_client.table("jobs").select("*")
    if status is not None:
        query = query.eq("status", status.value)
    rows = execute_query(
        query.order("created_at", desc=True),
        operation="list jobs",
    )
    return [JobRead.model_validate(row) for row in rows]


def update_job(job_id: UUID, patch: JobPatch) -> JobRead | None:
    values = patch.model_dump(mode="json", exclude_unset=True)
    rows = execute_query(
        supabase_client.table("jobs")
        .update(values)
        .eq("id", str(job_id))
        .select("*"),
        operation="update job",
    )
    return JobRead.model_validate(rows[0]) if rows else None