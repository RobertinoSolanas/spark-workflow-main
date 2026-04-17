import asyncio
from contextlib import asynccontextmanager

from event_logging.enums import EventAction, EventCategory, EventOutcome, LogEventSystem
from fastapi import FastAPI

from src.config.settings import settings
from src.models.db.database import AsyncSessionLocal
from src.models.db.file_enum import FileTypeEnum
from src.models.db.migrations.migrate import run_alembic_upgrade
from src.services.temporal.temporal_worker import start_temporal_worker
from src.utils.app_state import app_state
from src.utils.logger import logger
from src.utils.service_utils import (
    create_file_service,
    get_or_create_storage_provider,
    get_or_create_temporal_workflow_service,
)


def _register_background_task(task: asyncio.Task, task_name: str) -> None:
    """Track background task and log unexpected failures."""

    def _log_task_failure(done_task: asyncio.Task) -> None:
        if done_task.cancelled():
            return
        error = done_task.exception()
        if error is None:
            return
        logger.error(
            action=EventAction.NOTIFY,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.API,
            default_event=LogEventSystem.CONTAINER_LIFECYCLE,
            message=f"Background task '{task_name}' failed: {error}",
        )

    task.add_done_callback(_log_task_failure)
    app_state.background_tasks.append(task)


async def run_cleanup_loop() -> None:
    """
    Background task to clean up DMS.
    """
    while True:
        try:
            async with AsyncSessionLocal() as db:
                file_service = await create_file_service(db)
                deleted_ids = await file_service.clean_up(
                    retention_days=settings.CHECKPOINT_RETENTION_PERIOD_DAYS,
                    file_type=FileTypeEnum.TEMPORAL_CHECKPOINT,
                )
            logger.info(
                action=EventAction.DELETE,
                outcome=EventOutcome.SUCCESS,
                category=EventCategory.FILE,
                message=(f"Temporal checkpoint cleanup completed — deleted {len(deleted_ids)} files"),
            )
            logger.debug(
                action=EventAction.DELETE,
                outcome=EventOutcome.SUCCESS,
                category=EventCategory.FILE,
                message=f"Deleted files: {deleted_ids}",
            )
        except asyncio.CancelledError:
            logger.info(
                action=EventAction.NOTIFY,
                outcome=EventOutcome.UNKNOWN,
                category=EventCategory.FILE,
                message="Cleanup task cancelled during shutdown.",
            )
            raise
        except Exception as e:
            logger.error(
                action=EventAction.DELETE,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.FILE,
                message=f"Cleanup task failed (will retry later): {e}",
            )
        await asyncio.sleep(60 * 60 * 6)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Starts a background task."""
    try:
        run_alembic_upgrade()
    except Exception as e:
        logger.error(
            action=EventAction.HEALTH,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.API,
            default_event=LogEventSystem.CONTAINER_LIFECYCLE,
            message="Alembic migration failed",
            exc_info=True,
        )
        raise Exception from e

    try:
        cleanup_task = asyncio.create_task(run_cleanup_loop())
        _register_background_task(cleanup_task, "run_cleanup_loop")
    except Exception as e:
        logger.error(
            action=EventAction.HEALTH,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.API,
            default_event=LogEventSystem.CONTAINER_LIFECYCLE,
            message="Failed to start cleanup task",
            exc_info=True,
        )
        raise Exception from e

    try:
        temporal_worker_task = asyncio.create_task(start_temporal_worker())
        _register_background_task(temporal_worker_task, "start_temporal_worker")
    except Exception as e:
        logger.error(
            action=EventAction.HEALTH,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.API,
            default_event=LogEventSystem.CONTAINER_LIFECYCLE,
            message="Failed to start temporal worker",
            exc_info=True,
        )
        raise Exception from e

    storage_provider_service = await get_or_create_storage_provider()
    temporal_workflow_service = await get_or_create_temporal_workflow_service()

    app_state.temporal_workflow_service = temporal_workflow_service
    app_state.storage_provider_service = storage_provider_service
    app_state.startup_complete = True

    yield

    for task in app_state.background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    app_state.startup_complete = False
    await storage_provider_service.close()
    app_state.storage_provider_service = None
    app_state.temporal_workflow_service = None
