import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from temporal import start_temporal_worker

from src.config.settings import settings
from src.services.workflows import activities, workflows
from src.utils.app_state import app_state


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    ready = asyncio.Event()
    temporal_worker_task = asyncio.create_task(
        start_temporal_worker(
            host=settings.temporal.host,
            workflows=workflows,
            activities=activities,
            task_queue=settings.temporal.task_queue,
            namespace=settings.temporal.namespace,
            ready=ready,
        )
    )

    # Wait for worker to be ready, but also detect early failures
    done, _ = await asyncio.wait(
        [temporal_worker_task, asyncio.create_task(ready.wait())],
        return_when=asyncio.FIRST_COMPLETED,
    )
    # If the worker task finished before ready was set, it crashed
    if temporal_worker_task in done:
        temporal_worker_task.result()  # raises the exception

    app_state.startup_complete = True

    yield

    app_state.startup_complete = False
    temporal_worker_task.cancel()
