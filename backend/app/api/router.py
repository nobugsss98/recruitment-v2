from fastapi import APIRouter

from app.api.v1.jobs import router as jobs_router
from app.api.v1.candidates import router as candidates_router
from app.api.v1.applications import router as applications_router
from app.api.v1.interviews import router as interviews_router
from app.api.v1.auth import router as auth_router
from app.schemas.health_schema import HealthResponse


api_router = APIRouter()
api_v1_router = APIRouter(prefix="/api/v1", tags=["v1"])


@api_router.get("/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


api_v1_router.include_router(auth_router)
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(candidates_router)
api_v1_router.include_router(applications_router)
api_v1_router.include_router(interviews_router)
api_router.include_router(api_v1_router)
