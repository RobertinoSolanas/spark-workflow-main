import traceback
from contextlib import asynccontextmanager

from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
    LogEventSystem,
)
from fastapi import FastAPI

from src.models.db.migrations.migrate import run_alembic_upgrade
from src.utils.app_state import app_state
from src.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup actions"""
    try:
        run_alembic_upgrade()
    except Exception as e:
        logger.error(
            action=EventAction.HEALTH,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.API,
            default_event=LogEventSystem.CONTAINER_LIFECYCLE,
            message="Alembic migration failed",
            error_message=traceback.format_exc(),
        )
        raise Exception from e

    app_state.startup_complete = True

    yield

    app_state.startup_complete = False
