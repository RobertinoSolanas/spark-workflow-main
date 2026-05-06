# src/services/docling_processing/assembly.py
"""
Chunk combination, image deduplication, and debug file upload activities.
"""

import json
import logging
from datetime import timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from temporal import Base64Bytes
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.config import get_config
from src.processors.filter import HeaderFooterFilter
from src.providers.base import ContentItemDict
from src.services.docling_processing.extraction import DoclingChunkResult
from src.utils.dms_utils import (
    DmsUploadInput,
)
from src.utils.dms_utils import (
    upload_file as dms_upload_file,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic I/O Models
# =============================================================================


class CombineDoclingChunksInput(BaseModel):
    """Input for combine_docling_chunks activity."""

    chunk_results: list[DoclingChunkResult]
    project_id: UUID | None = None
    filename: str | None = None


class CombineDoclingChunksOutput(BaseModel):
    """Output from combine_docling_chunks activity.

    Markdown and content_list are always carried inline -- Temporal's S3
    payload codec transparently offloads serialized payloads >100KB.
    """

    md_content: str = ""
    content_list: list[ContentItemDict] = []
    images: dict[str, Base64Bytes] = {}  # Fallback only; empty when per-chunk upload succeeds
    image_refs: dict[str, str] = {}  # filename -> DMS file_id (lightweight refs)
    original_md_content: str | None = None
    provider_json: dict[str, Any] | None = None


class DeduplicateImagesInput(BaseModel):
    """Input for deduplicate_images activity."""

    content_list: list[ContentItemDict]
    images: dict[str, Base64Bytes]


class DeduplicateImagesOutput(BaseModel):
    """Output from deduplicate_images activity."""

    images: dict[str, Base64Bytes]
    duplicate_paths: list[str]


class UploadDebugFilesDoclingInput(BaseModel):
    """Input for upload_debug_files_docling activity."""

    content_list: list[ContentItemDict]
    provider_json: dict[str, Any] | None = None
    upload_folder: str
    stem: str
    project_id: UUID


# =============================================================================
# Activity Definitions
# =============================================================================


@activity.defn(name="combine_docling_chunks")
async def _combine_docling_chunks(
    input: CombineDoclingChunksInput,
) -> CombineDoclingChunksOutput:
    """
    Combine Docling chunk results into a single result.

    **Single chunk**: passes through directly (no-op).

    **Multiple chunks**: concatenates markdown strings and extends content
    lists in memory. Temporal's S3 payload codec transparently offloads
    the combined result if it exceeds 2MB.
    """
    if len(input.chunk_results) == 1:
        chunk = input.chunk_results[0]
        return CombineDoclingChunksOutput(
            md_content=chunk.md_content,
            content_list=chunk.content_list,
            images=chunk.images,
            image_refs=chunk.image_refs,
            original_md_content=chunk.original_md_content,
            provider_json=chunk.provider_json,
        )

    import re

    total = len(input.chunk_results)
    activity.logger.info(f"Combining {total} chunk results")

    def _offset_page_tags(md: str, offset: int) -> str:
        """Offset <seite nummer="X" /> tags in markdown by page_offset."""
        if offset == 0:
            return md

        def _replace(m: re.Match[str]) -> str:
            old_num = int(m.group(1))
            return f'<seite nummer="{old_num + offset}" />'

        return re.sub(r'<seite nummer="(\d+)" />', _replace, md)

    md_parts: list[str] = []
    combined_cl: list[ContentItemDict] = []
    all_image_refs: dict[str, str] = {}
    all_images: dict[str, bytes] = {}

    for i, chunk in enumerate(input.chunk_results):
        chunk_num = i + 1
        page_offset = chunk.page_offset

        md_parts.append(_offset_page_tags(chunk.md_content, page_offset))

        for item in chunk.content_list:
            if "page_idx" in item:
                item["page_idx"] = item["page_idx"] + page_offset
            combined_cl.append(item)

        all_images.update(chunk.images)
        all_image_refs.update(chunk.image_refs)

        activity.heartbeat(f"Combined {chunk_num}/{total} chunks")

    combined_md = "".join(md_parts)

    activity.logger.info(
        f"Combined {total} chunks: {len(combined_cl)} content items, "
        f"{len(all_image_refs)} image refs, {len(all_images)} fallback images"
    )

    return CombineDoclingChunksOutput(
        md_content=combined_md,
        content_list=combined_cl,
        images=all_images,
        image_refs=all_image_refs,
        original_md_content=None,
        provider_json=None,
    )


@activity.defn(name="deduplicate_images_docling")
async def _deduplicate_images(input: DeduplicateImagesInput) -> DeduplicateImagesOutput:
    """
    Deduplicate images using perceptual hashing.

    This is a CPU-intensive operation that uses imagehash to find similar images
    across the document (e.g., recurring logos, headers).

    Args:
        input: DeduplicateImagesInput with content_list and images

    Returns:
        DeduplicateImagesOutput with filtered images and list of duplicates
    """
    activity.logger.info(f"Deduplicating {len(input.images)} images")
    activity.heartbeat("Starting perceptual hashing")

    # Use the existing HeaderFooterFilter.find_duplicate_images
    # This handles perceptual hashing and grouping
    duplicate_img_paths = HeaderFooterFilter.find_duplicate_images(input.content_list, input.images)
    activity.heartbeat(f"Hashing complete, {len(duplicate_img_paths)} duplicates found")

    if not duplicate_img_paths:
        activity.logger.info("No duplicate images found")
        return DeduplicateImagesOutput(
            images=input.images,
            duplicate_paths=[],
        )

    # Filter out duplicates
    filtered_images = {
        k: v
        for k, v in input.images.items()
        if k not in duplicate_img_paths and f"images/{k}" not in duplicate_img_paths
    }

    activity.logger.info(
        f"Image dedup: {len(input.images)} -> {len(filtered_images)} images "
        f"({len(duplicate_img_paths)} duplicates removed)"
    )

    return DeduplicateImagesOutput(
        images=filtered_images,
        duplicate_paths=list(duplicate_img_paths),
    )


@activity.defn(name="upload_debug_files_docling")
async def _upload_debug_files_docling(input: UploadDebugFilesDoclingInput) -> None:
    """
    Upload JSON debug files to DMS.

    This activity handles JSON serialization in the activity context
    (not workflow thread) and uploads:
    - Provider JSON (if available)
    - Content list JSON

    Markdown files are not uploaded because the content is already
    persisted in the *_processed.json output.

    Args:
        input: UploadDebugFilesDoclingInput with content and upload parameters
    """
    activity.logger.info(f"Uploading debug files: {input.stem}")

    # Upload provider JSON (if available)
    if input.provider_json:
        provider_json_str = json.dumps(input.provider_json, ensure_ascii=False, indent=2)
        await dms_upload_file(
            DmsUploadInput(
                data=provider_json_str.encode("utf-8"),
                filename=f"{input.upload_folder}/{input.stem}_docling.json",
                project_id=input.project_id,
                file_type="content_extraction",
                content_type="application/json",
            )
        )

    # Upload content list JSON
    content_list_json = json.dumps(input.content_list, ensure_ascii=False, indent=2)
    await dms_upload_file(
        DmsUploadInput(
            data=content_list_json.encode("utf-8"),
            filename=f"{input.upload_folder}/{input.stem}_content_list.json",
            project_id=input.project_id,
            file_type="content_extraction",
            content_type="application/json",
        )
    )

    activity.logger.info(f"Uploaded debug files: {input.stem}_content_list.json")


# =============================================================================
# Workflow Wrappers
# =============================================================================


async def combine_docling_chunks(
    chunk_results: list[DoclingChunkResult],
    project_id: UUID | None = None,
    filename: str | None = None,
) -> CombineDoclingChunksOutput:
    """Workflow wrapper for combine_docling_chunks activity."""
    return await workflow.execute_activity(
        _combine_docling_chunks,
        CombineDoclingChunksInput(
            chunk_results=chunk_results,
            project_id=project_id,
            filename=filename,
        ),
        start_to_close_timeout=timedelta(minutes=15),
        heartbeat_timeout=timedelta(minutes=2),
        retry_policy=RetryPolicy(maximum_attempts=get_config().TEMPORAL_PROCESSING_ACTIVITY_MAX_ATTEMPTS),
    )


async def deduplicate_images(
    content_list: list[ContentItemDict],
    images: dict[str, bytes],
) -> DeduplicateImagesOutput:
    """Workflow wrapper for deduplicate_images activity."""
    return await workflow.execute_activity(
        _deduplicate_images,
        DeduplicateImagesInput(content_list=content_list, images=images),
        start_to_close_timeout=timedelta(minutes=10),
        heartbeat_timeout=timedelta(minutes=2),
        retry_policy=RetryPolicy(maximum_attempts=get_config().TEMPORAL_PROCESSING_ACTIVITY_MAX_ATTEMPTS),
    )


async def upload_debug_files_docling(
    content_list: list[ContentItemDict],
    provider_json: dict[str, Any] | None,
    upload_folder: str,
    stem: str,
    project_id: UUID,
) -> None:
    """Workflow wrapper for upload_debug_files_docling activity."""
    await workflow.execute_activity(
        _upload_debug_files_docling,
        UploadDebugFilesDoclingInput(
            content_list=content_list,
            provider_json=provider_json,
            upload_folder=upload_folder,
            stem=stem,
            project_id=project_id,
        ),
        start_to_close_timeout=timedelta(minutes=10),
        retry_policy=RetryPolicy(maximum_attempts=get_config().TEMPORAL_STORAGE_ACTIVITY_MAX_ATTEMPTS),
    )
