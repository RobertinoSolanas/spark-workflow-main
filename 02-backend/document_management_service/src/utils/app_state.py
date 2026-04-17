"""Class used to store current app state."""

from sqlalchemy.util.concurrency import asyncio

from src.services.storage_provider.storage_provider_base_service import (
    BaseStorageProviderService,
)
from src.services.temporal.temporal_service import TemporalWorkflowService


class AppState:
    def __init__(self):
        self.startup_complete = False
        self.storage_provider_service: BaseStorageProviderService | None = None
        self.temporal_workflow_service: TemporalWorkflowService | None = None
        self.background_tasks: list[asyncio.Task] = []


app_state = AppState()
