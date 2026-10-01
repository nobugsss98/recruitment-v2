from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import require_any_role
from app.database.crud import candidates_db
from app.schemas.candidates_schema import CandidateHistoryRecord

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get(
    "/{candidate_id}/history",
    response_model=list[CandidateHistoryRecord],
    dependencies=[Depends(require_any_role)],
)
def candidate_history_route(candidate_id: UUID) -> list[CandidateHistoryRecord]:
    return candidates_db.get_candidate_history(candidate_id)
