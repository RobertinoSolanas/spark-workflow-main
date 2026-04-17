from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
    LogEventDefault,
)

from src.config.settings import settings
from src.utils.logger import logger

temporal_client = None


async def get_temporal_client():
    from temporalio.client import Client
    from temporalio.contrib.pydantic import pydantic_data_converter

    global temporal_client
    if temporal_client is None:
        logger.info(
            action=EventAction.NOTIFY,
            outcome=EventOutcome.SUCCESS,
            category=EventCategory.API,
            default_event=LogEventDefault.GENERAL,
            message=(
                f"Connecting to Temporal at {settings.TEMPORAL.HOST} "
                f"with namespace {settings.TEMPORAL.NAMESPACE}"
            ),
        )
        temporal_client = await Client.connect(
            target_host=settings.TEMPORAL.HOST,
            namespace=settings.TEMPORAL.NAMESPACE,
            data_converter=pydantic_data_converter,
        )

    logger.info(
        action=EventAction.NOTIFY,
        outcome=EventOutcome.SUCCESS,
        category=EventCategory.API,
        default_event=LogEventDefault.GENERAL,
        message=(
            f"Successfully connected to Temporal at {settings.TEMPORAL.HOST} "
            f"with namespace {settings.TEMPORAL.NAMESPACE}"
        ),
    )
    return temporal_client
