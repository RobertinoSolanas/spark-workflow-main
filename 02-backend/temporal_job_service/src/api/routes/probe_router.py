from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from src.models.schemas.probe_schema import (
    CheckResponse,
    HealthStatus,
)
from src.utils.app_state import app_state

probe_router = APIRouter(tags=["probes"])


@probe_router.get(
    "/healthz",
    response_model=CheckResponse,
    response_model_exclude_unset=True,
)
def health_check():
    """Simple health check endpoint."""
    return CheckResponse(status="ok")


@probe_router.get(
    "/ready",
    response_model=CheckResponse,
    response_model_exclude_unset=True,
)
async def readiness_check():
    """
    Readiness probe: verifies database connectivity.
    """
    return CheckResponse(status="ok")


@probe_router.get(
    "/startup",
    response_model=CheckResponse,
    response_model_exclude_unset=True,
)
async def startup_check():
    """Startup probe: signals when application initialization is complete.

    Kubernetes will delay liveness/readiness probes until this succeeds.
    """
    if app_state.startup_complete:
        return CheckResponse(status="ok")

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=HealthStatus(
            status="starting",
            reason="startup in progress",
        ).model_dump(),
    )
