from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
)
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio.session import AsyncSession
from sqlalchemy.sql.expression import text

from src.models.db.database import get_db_session
from src.models.schemas.probe_schema import (
    CheckResponse,
    HealthStatus,
)
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
    db: AsyncSession = Depends(get_db_session),
):
    """
    Readiness probe: verifies database connectivity.
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
        await db.execute(text("SELECT 1"))
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
