# src/activities/postprocessing/dms_upload.py
"""
Temporal activities for DMS file operations (upload images, create final JSON, create summary).
"""

import asyncio
import mimetypes
import re
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel
from temporal import Base64Bytes
from temporal.workflows.inhaltsextraktion.types import (
    BaseMetadata,
    ProcessedFileInfo,
    SummaryData,
)
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.config import get_config
from src.schemas import (
    Chunk,
    Metadata,
    ProcessedDocument,
)
from src.utils.dms_utils import (
    DmsUploadInput,
    FileObject,
    ListFilesInput,
    delete_file,
    download_file,
    list_files,
    upload_file,
)
from src.utils.path_utils import get_output_dir
from src.workflows.summarization.output_format import SummaryOutput
from src.workflows.types import SingleDocumentWorkflowOutput


class UploadImagesToDmsInput(BaseModel):
    """Input for upload_images_to_dms activity."""

    images: dict[str, Base64Bytes]
    project_id: UUID
    filename: str


class CreateFinalJsonInput(BaseModel):
    """Input for create_final_json activity."""

    final_markdown: str
    chunks: list[Chunk]
    summary_result: SummaryOutput
    base_metadata: BaseMetadata | None
    original_filename: str
    project_id: UUID
    processing_duration_seconds: float
    source_file_id: str | None = None


class AssembleFinalJsonResult(BaseModel):
    """Result from assemble_and_upload_final_json activity."""

    final_json_file_id: UUID
    filename: str


class SummaryResult(BaseModel):
    """Result from create_summary_from_results activity."""

    summary_file_id: str
    filename: str
    summary_data: SummaryData


class CreateSummaryFromResultsInput(BaseModel):
    """Input for create_summary_from_results activity."""

    results: list[SingleDocumentWorkflowOutput]
    project_id: UUID
    base_metadata: BaseMetadata | None
    total_duration_seconds: float = 0.0


# --- Helpers ---


async def _upload_image_to_dms(
    img_filename: str,
    img_bytes: bytes,
    *,
    semaphore: asyncio.Semaphore,
    upload_folder: str,
    project_id: UUID,
    suppress_errors: bool = True,
) -> FileObject | None:
    """Upload a single image to DMS with semaphore-gated concurrency.

    Returns FileObject on success.  When *suppress_errors* is True (default),
    failures are logged as warnings and None is returned.  When False,
    exceptions propagate to the caller unchanged.
    """
    async with semaphore:
        img_content_type, _ = mimetypes.guess_type(img_filename)
        if not img_content_type:
            img_content_type = "image/png"

        try:
            return await upload_file(
                DmsUploadInput(
                    data=img_bytes,
                    filename=f"{upload_folder}/images/{img_filename}",
                    project_id=project_id,
                    file_type="content_extraction",
                    content_type=img_content_type,
                )
            )
        except Exception as e:
            if not suppress_errors:
                raise
            activity.logger.warning(f"Failed to upload image {img_filename}: {e}")
            return None


# --- Activity definitions ---


@activity.defn(name="create_summary_from_results")
async def _create_summary_from_results(
    input: CreateSummaryFromResultsInput,
) -> SummaryResult:
    """
    Downloads all processed JSON files from DMS, compiles them into a summary,
    and uploads/merges the summary back to DMS.

    If summary.json already exists, merges new data with existing content.
    Otherwise creates a new summary.json file.

    Returns:
        SummaryResult with file_id of the summary JSON
    """
    summary_filename = "summary.json"

    # Build processed file details from the current batch
    new_processed_files: list[ProcessedFileInfo] = []
    for result in input.results:
        new_processed_files.append(
            ProcessedFileInfo(
                document_name=result.document_name,
                document_path=result.document_path,
                processed_json_file_id=str(result.final_json_file_id),
            )
        )

    # Try to load existing summary.json and merge
    existing_summary: SummaryData | None = None
    existing_file_id = None
    # List files to find existing summary.json
    files = await list_files(ListFilesInput(project_id=input.project_id, file_type="content_extraction"))
    for file_obj in files:
        if file_obj.filename == summary_filename:
            existing_file_id = file_obj.id
            try:
                existing_bytes = await download_file(existing_file_id)
                existing_summary = SummaryData.model_validate_json(existing_bytes)
                activity.logger.info("Found existing summary.json, will merge contents")
            except FileNotFoundError:
                activity.logger.warning(
                    f"Found summary.json metadata (file_id={existing_file_id}) but file "
                    f"not found in storage — likely orphaned from a previous failed run. "
                    f"Creating a fresh summary."
                )
                existing_file_id = None
            break

    if existing_summary:
        # Merge with existing summary
        # Merge processed files: replace entries with same document_name
        # Use dict keyed by document_name, existing first then new (new overwrites)
        processed_by_name = {p.document_name: p for p in existing_summary.processed_files}
        for new_file in new_processed_files:
            processed_by_name[new_file.document_name] = new_file
        merged_processed = list(processed_by_name.values())

        merged_duration = existing_summary.total_duration_seconds + input.total_duration_seconds

        # Use new base_metadata if provided, otherwise keep existing
        merged_base_metadata = input.base_metadata if input.base_metadata else existing_summary.base_metadata

        summary_data = SummaryData(
            base_metadata=merged_base_metadata,
            total_duration_seconds=merged_duration,
            processed_files=merged_processed,
        )
    else:
        # Create new summary
        summary_data = SummaryData(
            base_metadata=input.base_metadata,
            total_duration_seconds=input.total_duration_seconds,
            processed_files=new_processed_files,
        )

    summary_json_str = summary_data.model_dump_json(indent=2)
    summary_file_bytes = summary_json_str.encode("utf-8")

    # Upload new summary to DMS first, then delete old one.
    # This order is important: if the upload fails and Temporal retries
    # the activity, the old file is still available for download/merge.
    file_obj = await upload_file(
        DmsUploadInput(
            data=summary_file_bytes,
            filename=summary_filename,
            project_id=input.project_id,
            file_type="content_extraction",
            content_type="application/json",
        )
    )

    # Delete old summary.json after successful upload
    if existing_file_id:
        try:
            await delete_file(existing_file_id)
            activity.logger.info(f"Deleted old summary.json: {existing_file_id}")
        except Exception as e:
            activity.logger.warning(f"Failed to delete old summary.json: {e}")

    return SummaryResult(
        summary_file_id=str(file_obj.id),
        filename=summary_filename,
        summary_data=summary_data,
    )


@activity.defn(name="upload_images_to_dms")
async def _upload_images_to_dms(input: UploadImagesToDmsInput) -> int:
    """
    Upload extracted images to DMS for frontend consumption.

    Runs as a separate activity with heartbeats so Temporal can track
    progress and detect stuck uploads. Uses a semaphore to upload
    multiple images concurrently without overwhelming DMS.
    """
    upload_folder = get_output_dir(input.filename)
    uploaded = 0
    total = len(input.images)
    semaphore = asyncio.Semaphore(get_config().MAX_CONCURRENT_DMS_IMAGE_UPLOADS)

    async def _do_upload(name: str, data: bytes) -> None:
        nonlocal uploaded
        await _upload_image_to_dms(
            name,
            data,
            semaphore=semaphore,
            upload_folder=upload_folder,
            project_id=input.project_id,
            suppress_errors=False,
        )
        uploaded += 1
        activity.heartbeat(f"Uploaded {uploaded}/{total} images")

    await asyncio.gather(*[_do_upload(name, data) for name, data in input.images.items()])

    activity.logger.info(f"Uploaded {uploaded} images to DMS")
    return uploaded


@activity.defn(name="create_final_json")
async def _create_final_json(input: CreateFinalJsonInput) -> AssembleFinalJsonResult:
    """
    Assembles the final processed document JSON and uploads it to DMS.

    This is an activity because model_dump_json() on large documents is CPU-intensive
    and would block the workflow thread, causing deadlocks.
    """
    final_markdown = input.final_markdown
    chunks = input.chunks
    summary_result = input.summary_result
    base_metadata = input.base_metadata
    original_filename = input.original_filename
    processing_duration = input.processing_duration_seconds
    project_id = input.project_id

    # Find all page markers and get the maximum page number
    page_numbers = [int(m) for m in re.findall(r'<seite nummer="(\d+)"\s*/>', final_markdown)]
    page_count = max(page_numbers) if page_numbers else None

    metadata_payload = {
        "original_document_name": original_filename,
        "source_file_id": input.source_file_id,
        "project_id": str(project_id),
        "pages": page_count,
        "base_metadata": base_metadata.model_dump() if base_metadata else None,
        "summary": summary_result.summary,
        "processing_duration_seconds": processing_duration,
    }

    metadata = Metadata(**metadata_payload)
    processed_document = ProcessedDocument(metadata=metadata, markdown_content=final_markdown, chunks=chunks)

    activity.heartbeat("Serializing final JSON")
    json_bytes = processed_document.model_dump_json(indent=4).encode("utf-8")
    activity.heartbeat(f"Serialized {len(json_bytes) / (1024 * 1024):.1f} MB, uploading")

    # Get output directory (mirrors input folder structure) and stem for filename
    doc_stem = get_output_dir(original_filename)
    stem = Path(original_filename).stem
    output_filename = f"{doc_stem}/{stem}_processed.json"

    file_obj = await upload_file(
        DmsUploadInput(
            data=json_bytes,
            filename=output_filename,
            project_id=project_id,
            file_type="content_extraction",
            content_type="application/json",
        )
    )

    return AssembleFinalJsonResult(
        final_json_file_id=file_obj.id,
        filename=output_filename,
    )


# --- Workflow wrappers ---


async def upload_images_to_dms(
    images: dict[str, Base64Bytes],
    project_id: UUID,
    filename: str,
) -> int:
    """Workflow wrapper for upload_images_to_dms activity."""
    return await workflow.execute_activity(
        _upload_images_to_dms,
        UploadImagesToDmsInput(
            images=images,
            project_id=project_id,
            filename=filename,
        ),
        start_to_close_timeout=timedelta(minutes=30),
        heartbeat_timeout=timedelta(minutes=2),
        retry_policy=RetryPolicy(maximum_attempts=get_config().TEMPORAL_STORAGE_ACTIVITY_MAX_ATTEMPTS),
    )


async def create_final_json(input: CreateFinalJsonInput) -> AssembleFinalJsonResult:
    """Workflow wrapper for create_final_json activity."""
    return await workflow.execute_activity(
        _create_final_json,
        input,
        start_to_close_timeout=timedelta(minutes=5),
        heartbeat_timeout=timedelta(minutes=3),
        retry_policy=RetryPolicy(maximum_attempts=get_config().TEMPORAL_STORAGE_ACTIVITY_MAX_ATTEMPTS),
    )


async def create_summary_from_results(
    input: CreateSummaryFromResultsInput,
) -> SummaryResult:
    """Workflow wrapper for DMS create_summary_from_results."""
    return await workflow.execute_activity(
        _create_summary_from_results,
        input,
        start_to_close_timeout=timedelta(minutes=5),
        retry_policy=RetryPolicy(maximum_attempts=get_config().TEMPORAL_PROCESSING_ACTIVITY_MAX_ATTEMPTS),
    )
