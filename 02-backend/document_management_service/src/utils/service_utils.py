from sqlalchemy.ext.asyncio import AsyncSession

from src.services.files.file_service import FileService
from src.services.storage_provider.storage_provider_s3_service import (
    AsyncS3StorageClient,
)
from src.services.temporal.temporal_service import TemporalWorkflowService
from src.services.zip_files.zip_file_service import ZipFileService
from src.utils.app_state import app_state


async def get_or_create_storage_provider():
    """Return shared storage provider from app state or initialize a new one."""
    storage_provider_service = app_state.storage_provider_service
    if storage_provider_service is None:
        storage_provider_service = AsyncS3StorageClient()
        await storage_provider_service.initialize()
        app_state.storage_provider_service = storage_provider_service
    return storage_provider_service


async def get_or_create_temporal_workflow_service() -> TemporalWorkflowService:
    """Return temporal workflow service from app state or initialize a new one."""
    temporal_workflow_service = app_state.temporal_workflow_service
    if temporal_workflow_service is None:
        temporal_workflow_service = TemporalWorkflowService()
        app_state.temporal_workflow_service = temporal_workflow_service
    return temporal_workflow_service


async def create_file_service(db: AsyncSession) -> FileService:
    """Build FileService with shared storage provider and given DB session."""
    storage_provider_service = await get_or_create_storage_provider()
    temporal_workflow_service = await get_or_create_temporal_workflow_service()
    return FileService(
        db=db,
        storage_provider_service=storage_provider_service,
        temporal_workflow_service=temporal_workflow_service,
    )


async def create_zip_file_service(db: AsyncSession) -> ZipFileService:
    """Build FileService with shared storage provider and given DB session."""
    storage_provider_service = await get_or_create_storage_provider()
    return ZipFileService(
        db=db,
        storage_provider_service=storage_provider_service,
    )
