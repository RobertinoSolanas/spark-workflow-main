from collections.abc import Callable, Sequence

from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
    LogEventDefault,
)

from src.config.settings import settings
from src.services.temporal.temporal_client import get_temporal_client
from src.services.workflows import workflows
from src.services.workflows.activities import activities
from src.utils.logger import logger


async def start_temporal_worker(
    wfs: Sequence[type] = workflows,
    acts: Sequence[Callable] = activities,
) -> None:
    from temporalio.worker import UnsandboxedWorkflowRunner, Worker

    worker = Worker(
        await get_temporal_client(),
        task_queue=settings.TEMPORAL.TASK_QUEUE,
        workflows=wfs,
        activities=acts,
        workflow_runner=UnsandboxedWorkflowRunner(),
    )

    logger.info(
        action=EventAction.NOTIFY,
        outcome=EventOutcome.SUCCESS,
        category=EventCategory.API,
        default_event=LogEventDefault.GENERAL,
        message=(
            f"Temporal worker starting on task queue '{settings.TEMPORAL.TASK_QUEUE}'"
        ),
    )
    await worker.run()
