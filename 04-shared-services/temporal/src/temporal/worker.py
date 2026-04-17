import asyncio
import logging
from collections.abc import Callable, Sequence
from typing import Any, override

from event_logging.settings import Environment
from temporalio import activity
from temporalio.client import Client
from temporalio.contrib.pydantic import PydanticPayloadConverter
from temporalio.converter import DataConverter
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from temporal.custom_otel_plugin import CustomOtelPlugin
from temporal.interceptors import LoggingInterceptor
from temporal.logging_setup import setup_event_logging
from temporal.payload_codec import LargePayloadCodec
from temporal.s3_payload_storage import S3PayloadStorage

logger = logging.getLogger("temporal.worker")
logger.setLevel(logging.DEBUG)


class IgnorePydanticValidation(logging.Filter):
    @override
    def filter(self, record: logging.LogRecord) -> bool:
        return "ValidationError" not in record.getMessage()


class IgnoreDecodeFailures(logging.Filter):
    @override
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "Failed activation on workflow" in msg and "Failed decoding arguments" in msg:
            return False
        return True


activity.logger.base_logger.addFilter(IgnorePydanticValidation())
logging.getLogger("temporalio.worker._workflow_instance").addFilter(IgnoreDecodeFailures())


_client: Client | None = None
_client_lock = asyncio.Lock()


async def create_temporal_client(
    host: str,
    namespace: str = "default",
    storage: S3PayloadStorage | None = None,
) -> Client:
    """Create a Temporal client with Pydantic payload conversion and OTel plugin.

    When storage is provided, payloads larger than 100KB are offloaded to S3.
    """
    payload_codec = LargePayloadCodec(storage) if storage else None
    payload_converter = DataConverter(
        payload_converter_class=PydanticPayloadConverter,
        payload_codec=payload_codec,
    )
    return await Client.connect(
        target_host=host,
        namespace=namespace,
        data_converter=payload_converter,
        plugins=[CustomOtelPlugin()],
    )


async def get_temporal_client(
    host: str | None = None,
    namespace: str = "default",
    storage: S3PayloadStorage | None = None,
) -> Client:
    """Return the global Temporal client, creating it on first call.

    First call must provide host. Subsequent calls return the cached singleton.
    """
    global _client
    if _client is not None:
        return _client
    async with _client_lock:
        if _client is not None:
            return _client
        if host is None:
            raise RuntimeError("Temporal client not initialized. First call must provide host.")
        _client = await create_temporal_client(host, namespace, storage)
    return _client


async def start_temporal_worker(
    host: str,
    workflows: Sequence[type[Any]],
    activities: Sequence[Callable[..., Any]],
    task_queue: str,
    storage: S3PayloadStorage | None = None,
    namespace: str = "default",
    max_concurrent_activities: int | None = None,
    max_task_queue_activities_per_second: int | None = None,
    ready: asyncio.Event | None = None,
) -> None:
    """Start a Temporal worker with the given configuration.

    The worker runs in unsandboxed mode for smoother integration.

    If ready is provided, it is set once the client is connected and the
    worker is about to start polling. Callers can await ready.wait() to
    know the client is available via get_temporal_client().
    """
    setup_event_logging(task_queue)
    logger.info(f"Connecting to temporal at {host} with namespace {namespace}")

    client = await get_temporal_client(host, namespace, storage)

    env = Environment.DEVELOPMENT if "localhost" in host else Environment.PRODUCTION
    interceptors = [LoggingInterceptor(service_name=task_queue, env=env)]
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=workflows,
        activities=activities,
        workflow_runner=UnsandboxedWorkflowRunner(),
        interceptors=interceptors,
        debug_mode=True,
        max_concurrent_activities=max_concurrent_activities,
        max_task_queue_activities_per_second=max_task_queue_activities_per_second,
    )

    if ready is not None:
        ready.set()

    try:
        await worker.run()
    finally:
        if storage:
            await storage.close()
