from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
)
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.sql.expression import text

from src.api.dependencies import get_file_service
from src.models.schemas.probe_schema import (
    CheckResponse,
    HealthStatus,
)
from src.services.files.file_service import FileService
from src.utils.app_state import app_state
from src.utils.logger import logger

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
async def readiness_check(
    service: FileService = Depends(get_file_service),
):
    """
    Readiness and liveness probe: verifies storage bucket and database connectivity.
    """
    if not app_state.startup_complete:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=HealthStatus(
                status="not ready",
                reason="startup not complete",
            ).model_dump(),
        )

    # Database check
    try:
        await service.db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(
            action=EventAction.VALIDATE,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.DATABASE,
            message=f"Database check failed: {e}",
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=HealthStatus(
                status="not ready",
                reason="database unreachable",
            ).model_dump(),
        )

    # Storage check
    try:
        exists = await service.storage_provider_service.bucket_exists()
    except Exception as e:
        logger.error(
            action=EventAction.VALIDATE,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.FILE,
            message=f"Storage check failed: {e}",
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=HealthStatus(
                status="not ready",
                reason="storage unreachable",
            ).model_dump(),
        )

    if not exists:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=HealthStatus(
                status="not ready",
                reason="bucket not found or inaccessible",
            ).model_dump(),
        )

    return CheckResponse(status="ok")  # type: ignore


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
