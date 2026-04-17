"""
Temporal activities for DMS (Document Management Service) operations.

These activities handle file uploads and downloads through the DMS service,
using file_ids (UUIDs) instead of str types.
"""

from datetime import timedelta
from uuid import UUID

from pydantic import BaseModel
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.config import get_config
from src.utils.dms_utils import (
    DmsUploadInput,
    FileObject,
    ListFilesInput,
    delete_file,
    download_file,
    get_file_metadata,
    list_files,
    upload_file,
)

# --- Pydantic models for activity I/O ---


class DmsFileInfo(BaseModel):
    """Simplified file info to pass between activities."""

    file_id: str
    filename: str
    mime_type: str
    bucket_path: str

    @classmethod
    def from_file_object(cls, obj: FileObject) -> "DmsFileInfo":
        """Create a DmsFileInfo instance from a DMS FileObject."""
        return cls(
            file_id=str(obj.id),
            filename=obj.filename,
            mime_type=obj.mime_type,
            bucket_path=str(obj.bucket_path),
        )


class DmsUploadResult(BaseModel):
    """Result of a DMS upload operation."""

    file_id: UUID
    filename: str
    bucket_path: str


# --- Activity Definitions ---


@activity.defn(name="dms_download_file")
async def _download_file_activity(file_id: UUID) -> bytes:
    """Download a file's content from DMS by its UUID."""
    return await download_file(file_id)


@activity.defn(name="dms_get_file_metadata")
async def _get_file_metadata_activity(file_id: UUID) -> DmsFileInfo:
    """Retrieve file metadata from DMS and return it as DmsFileInfo."""
    file_obj = await get_file_metadata(file_id)
    return DmsFileInfo.from_file_object(file_obj)


@activity.defn(name="dms_upload_file")
async def _upload_file_activity(
    input: DmsUploadInput,
) -> DmsUploadResult:
    """Upload a file to DMS and return the upload result."""
    file_obj = await upload_file(input)

    return DmsUploadResult(
        file_id=file_obj.id,
        filename=file_obj.filename,
        bucket_path=str(file_obj.bucket_path),
    )


@activity.defn(name="dms_list_files")
async def _list_files_activity(
    input: ListFilesInput,
) -> list[DmsFileInfo]:
    """List files in a DMS directory and return them as DmsFileInfo objects."""
    files = await list_files(input)
    return [DmsFileInfo.from_file_object(f) for f in files]


@activity.defn(name="dms_delete_file")
async def _delete_file_activity(file_id: UUID) -> None:
    """Delete a file from DMS by its UUID."""
    await delete_file(file_id)


@activity.defn(name="dms_resolve_priority_file")
async def _resolve_priority_file(candidates: list[DmsFileInfo]) -> DmsFileInfo:
    """Download each candidate and return the one with the most bytes."""
    if not candidates:
        raise ValueError("resolve_priority_file called with empty candidates list")

    sizes: list[tuple[DmsFileInfo, int]] = []
    for candidate in candidates:
        data = await download_file(UUID(candidate.file_id))
        size = len(data)
        activity.logger.info(f"Priority candidate '{candidate.filename}' ({candidate.file_id}): {size} bytes")
        sizes.append((candidate, size))

    winner = max(sizes, key=lambda t: t[1])
    activity.logger.info(f"Selected priority file: '{winner[0].filename}' ({winner[0].file_id}) with {winner[1]} bytes")
    return winner[0]


# --- Workflow-Facing Wrappers ---


async def dms_download_file(file_id: UUID) -> bytes:
    """Workflow wrapper to download a file from DMS."""
    return await workflow.execute_activity(
        _download_file_activity,
        file_id,
        start_to_close_timeout=timedelta(minutes=5),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_STORAGE_ACTIVITY_MAX_ATTEMPTS,
            non_retryable_error_types=["FileNotFoundError"],
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=60),
        ),
    )


async def dms_get_file_metadata(file_id: UUID) -> DmsFileInfo:
    """Workflow wrapper to retrieve file metadata from DMS."""
    return await workflow.execute_activity(
        _get_file_metadata_activity,
        file_id,
        start_to_close_timeout=timedelta(seconds=60),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_STORAGE_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=60),
        ),
    )


async def dms_upload_file(input: DmsUploadInput) -> DmsUploadResult:
    """Workflow wrapper to upload a file to DMS."""
    return await workflow.execute_activity(
        _upload_file_activity,
        input,
        start_to_close_timeout=timedelta(minutes=5),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_STORAGE_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=60),
        ),
    )


async def dms_list_files(
    input: ListFilesInput,
) -> list[DmsFileInfo]:
    """Workflow wrapper to list files in a DMS directory."""
    return await workflow.execute_activity(
        _list_files_activity,
        input,
        start_to_close_timeout=timedelta(seconds=60),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_STORAGE_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=60),
        ),
    )


async def dms_delete_file(file_id: UUID) -> None:
    """Workflow wrapper to delete a file from DMS."""
    await workflow.execute_activity(
        _delete_file_activity,
        file_id,
        start_to_close_timeout=timedelta(seconds=60),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_STORAGE_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=60),
        ),
    )


async def resolve_priority_file(candidates: list[DmsFileInfo]) -> DmsFileInfo:
    """Workflow wrapper to resolve the priority file from multiple candidates by size."""
    return await workflow.execute_activity(
        _resolve_priority_file,
        candidates,
        start_to_close_timeout=timedelta(minutes=5),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_STORAGE_ACTIVITY_MAX_ATTEMPTS,
            non_retryable_error_types=["ValueError"],
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=60),
        ),
    )
