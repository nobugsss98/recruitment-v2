from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    get_current_user,
    require_any_role,
    require_ceo,
    require_hr,
)
from app.database.crud import candidates_db, interviews_db
from app.schemas.auth_schema import UserRead
from app.schemas.candidates_schema import (
    ApplicationDossier,
    ApplicationRead,
    FinalDecisionRequest,
    HROverrideRequest,
)
from app.services import audit
from app.utils.logging import get_logger

router = APIRouter(prefix="/applications", tags=["applications"])
_logger = get_logger("app.applications")


@router.post(
    "/{application_id}/hr-override",
    response_model=ApplicationRead,
    dependencies=[Depends(require_hr)],
)
def hr_override_route(
    application_id: UUID,
    request: HROverrideRequest,
    current_user: UserRead = Depends(get_current_user),
) -> ApplicationRead:
    try:
        row = candidates_db.apply_hr_pass_override(application_id, hr_username=request.hr_username)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    if row is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="application is not an eligible sync failure")
    _logger.info("hr override applied", application_id=str(application_id))
    audit.record_audit(
        action="hr_override",
        entity="application",
        entity_id=application_id,
        actor=current_user,
        metadata={"hr_username": request.hr_username},
    )
    return row


@router.post(
    "/{application_id}/move-to-ceo",
    response_model=ApplicationRead,
    dependencies=[Depends(require_hr)],
)
def move_to_ceo_route(application_id: UUID) -> ApplicationRead:
    rounds = interviews_db.list_interview_rounds(application_id)
    if not rounds:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="at least one interview is required")
    if any(round_.status.value != "complete" for round_ in rounds):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="all interviews must be complete")
    row = candidates_db.move_application_to_ceo(application_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="application is not ready for CEO review")
    return row


@router.get(
    "/{application_id}/dossier",
    response_model=ApplicationDossier,
    dependencies=[Depends(require_any_role)],
)
def dossier_route(application_id: UUID) -> ApplicationDossier:
    application = candidates_db.get_application(application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="application not found")
    return ApplicationDossier(application=application, interviews=interviews_db.list_interview_rounds(application_id))


@router.post(
    "/{application_id}/final-decision",
    response_model=ApplicationRead,
    dependencies=[Depends(require_ceo)],
)
def final_decision_route(
    application_id: UUID,
    request: FinalDecisionRequest,
    current_user: UserRead = Depends(get_current_user),
) -> ApplicationRead:
    if request.final_decision.value == "pending":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="final decision must be pass or fail")
    row = candidates_db.save_final_decision(
        application_id,
        final_decision=request.final_decision.value,
        remarks=request.remarks,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="application is not ready for final decision")
    _logger.info(
        "final decision saved",
        application_id=str(application_id),
        decision=request.final_decision.value,
    )
    audit.record_audit(
        action="final_decision",
        entity="application",
        entity_id=application_id,
        actor=current_user,
        metadata={"final_decision": request.final_decision.value},
    )
    return row
