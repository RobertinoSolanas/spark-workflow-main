# src/services/docling_processing/extraction.py
"""
Docling chunk extraction activity.
"""

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from temporal import Base64Bytes
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.config import get_config, get_docling_url
from src.providers.base import ContentItemDict
from src.providers.docling.api_client import DoclingApiClient
from src.providers.docling.content_builder import ContentBuilder
from src.providers.docling.extractors import ImageExtractor, TableExtractor
from src.providers.docling.markdown_builder import MarkdownBuilder
from src.providers.docling.transforms import sanitize_output_prefix
from src.utils.dms_utils import (
    DmsUploadInput,
)
from src.utils.dms_utils import (
    upload_file as dms_upload_file,
)
from src.utils.path_utils import get_output_dir

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic I/O Models
# =============================================================================


class ExtractChunkInput(BaseModel):
    """Input for extract_chunk_with_docling activity."""

    chunk_bytes: Base64Bytes
    chunk_index: int
    total_chunks: int
    page_offset: int  # Starting page number for this chunk
    output_prefix: str
    filename: str
    project_id: UUID | None = None  # For direct provider_json upload


class DoclingChunkResult(BaseModel):
    """Result from processing a single chunk with Docling.

    For split documents, images are uploaded to DMS per-chunk.
    Markdown and content_list are always carried inline -- Temporal's S3
    payload codec transparently offloads serialized payloads >100KB.
    """

    md_content: str = ""
    content_list: list[ContentItemDict] = []
    images: dict[str, Base64Bytes] = {}  # Fallback only; empty when per-chunk upload succeeds
    image_refs: dict[str, str] = {}  # filename -> DMS file_id (lightweight refs)
    original_md_content: str | None = None
    provider_json: dict[str, Any] | None = None
    page_offset: int = 0


# =============================================================================
# Activity Definitions
# =============================================================================


@activity.defn(name="extract_chunk_with_docling")
async def _extract_chunk_with_docling(input: ExtractChunkInput) -> DoclingChunkResult:
    """
    Extract content from a single PDF chunk using docling-serve API.

    This activity handles:
    - Calling docling-serve API
    - Extracting images from JSON/markdown
    - Extracting tables with HTML
    - Cropping table images from PDF
    - Building custom markdown
    - Building content list

    Args:
        input: ExtractChunkInput with chunk bytes and metadata

    Returns:
        DoclingChunkResult with markdown, content list, and images
    """
    chunk_num = input.chunk_index + 1
    activity.logger.info(f"Processing chunk {chunk_num}/{input.total_chunks} (page offset: {input.page_offset})")

    # Get docling URL
    docling_url = get_docling_url()
    if not docling_url:
        raise RuntimeError(
            "DOCLING_URL not configured. Set DOCLING_HOST environment variable to point to docling-serve API."
        )

    # Sanitize output prefix
    output_prefix = sanitize_output_prefix(input.output_prefix)
    if input.total_chunks > 1:
        output_prefix = f"{output_prefix}_chunk{chunk_num}"

    cfg = get_config()

    # Initialize API client and call docling-serve
    api_client = DoclingApiClient(docling_url, cfg.DOCLING_TIMEOUT)
    result = await api_client.convert_document(
        input.chunk_bytes,
        input.filename,
        heartbeat_fn=activity.heartbeat,
        log_fn=activity.logger.info,
    )

    doc_data = result.get("document", {})
    doc_json = doc_data.get("json_content", {})
    original_md = doc_data.get("md_content", "")

    if not doc_json:
        raise RuntimeError("docling-serve returned empty json_content")

    activity.logger.info(
        f"docling-serve returned {len(doc_json.get('texts', []))} texts, "
        f"{len(doc_json.get('tables', []))} tables, "
        f"{len(doc_json.get('pictures', []))} pictures"
    )

    # Extract images from embedded base64 in JSON
    images_meta, images_bytes = ImageExtractor.extract_from_json(doc_json, output_prefix)

    # If no images in JSON, try extracting from markdown
    if not images_bytes and original_md:
        activity.logger.info("No images in JSON, extracting from markdown content")
        images_meta, images_bytes = ImageExtractor.extract_from_markdown(original_md, doc_json, output_prefix)

    # Extract tables (HTML from JSON structure)
    tables_meta = TableExtractor.extract_from_json(doc_json, output_prefix, images_bytes)

    # Crop table images from PDF if docling-serve didn't provide them
    # Wrap in asyncio.to_thread since PDF rendering is CPU-bound
    if cfg.DOCLING_TABLE_AS_IMAGE:
        await asyncio.to_thread(
            TableExtractor.crop_table_images,
            pdf_bytes=input.chunk_bytes,
            doc_json=doc_json,
            tables_meta=tables_meta,
            images_bytes=images_bytes,
            output_prefix=output_prefix,
        )

    # Build custom markdown
    custom_md = MarkdownBuilder.build(
        doc_json=doc_json,
        images_meta=images_meta,
        tables_meta=tables_meta,
    )

    # Build content list from JSON
    content_list = ContentBuilder.build_from_json(
        doc_json=doc_json,
        images_meta=images_meta,
        tables_meta=tables_meta,
    )

    # Detect and inject full-page images for pages where docling missed dominant images
    if cfg.DETECT_FULL_PAGE_IMAGES:
        images_meta, images_bytes, content_list, custom_md = ImageExtractor.inject_full_page_images(
            doc_json=doc_json,
            images_meta=images_meta,
            images_bytes=images_bytes,
            content_list=content_list,
            markdown=custom_md,
            output_prefix=output_prefix,
        )

    activity.logger.info(
        f"Chunk {chunk_num} extraction complete: {len(content_list)} content items, {len(images_bytes)} images"
    )

    upload_folder = get_output_dir(input.filename)
    stem = input.output_prefix

    # Upload provider_json directly to DMS to avoid carrying it through
    # the combine step (1-5MB per chunk accumulates to hundreds of MB)
    uploaded_provider_json = None
    if input.project_id is not None and doc_json:
        project_id = input.project_id
        try:
            json_bytes = json.dumps(doc_json, ensure_ascii=False, indent=2).encode("utf-8")
            await dms_upload_file(
                DmsUploadInput(
                    data=json_bytes,
                    filename=f"{upload_folder}/{stem}_docling.json",
                    project_id=project_id,
                    file_type="content_extraction",
                    content_type="application/json",
                )
            )
            activity.logger.info(f"Uploaded provider_json for chunk {chunk_num} directly to DMS")
        except Exception as e:
            activity.logger.warning(f"Failed to upload provider_json for chunk {chunk_num}: {e}")
            # Fall back to carrying it through (backward compat)
            uploaded_provider_json = doc_json

    # --- Upload strategy ---
    # TODO: Change when deduplicated codec is implemented -- images can then
    #  be carried inline without duplicating bytes across chunks.
    # Images are uploaded to DMS per-chunk for split documents to avoid
    # carrying GB of image bytes through Temporal payloads.
    # Markdown and content_list are always carried inline -- Temporal's S3
    # payload codec transparently offloads serialized payloads >100KB.
    is_split_doc = input.total_chunks > 1 and input.project_id is not None

    image_refs: dict[str, str] = {}
    fallback_images: dict[str, bytes] = {}

    if is_split_doc and images_bytes and input.project_id is not None:
        import mimetypes

        split_project_id = input.project_id
        activity.logger.info(f"Chunk {chunk_num}: uploading {len(images_bytes)} images to DMS (split-doc path)")
        upload_semaphore = asyncio.Semaphore(cfg.MAX_CONCURRENT_DMS_IMAGE_UPLOADS)

        async def _upload_image(img_name: str, img_data: bytes) -> None:
            async with upload_semaphore:
                img_content_type, _ = mimetypes.guess_type(img_name)
                if not img_content_type:
                    img_content_type = "image/png"
                try:
                    file_obj = await dms_upload_file(
                        DmsUploadInput(
                            data=img_data,
                            filename=f"{upload_folder}/images/{img_name}",
                            project_id=split_project_id,
                            file_type="content_extraction",
                            content_type=img_content_type,
                        )
                    )
                    image_refs[img_name] = str(file_obj.id)
                except Exception as e:
                    activity.logger.warning(f"Failed to upload image {img_name} for chunk {chunk_num}: {e}")
                    fallback_images[img_name] = img_data

        await asyncio.gather(*[_upload_image(name, data) for name, data in images_bytes.items()])
        activity.logger.info(
            f"Chunk {chunk_num}: uploaded {len(image_refs)}/{len(images_bytes)} images to DMS"
            + (f" ({len(fallback_images)} kept as fallback)" if fallback_images else "")
        )
    else:
        fallback_images = images_bytes

    return DoclingChunkResult(
        md_content=custom_md,
        content_list=content_list,
        images=fallback_images,
        image_refs=image_refs,
        original_md_content=original_md,
        provider_json=uploaded_provider_json,
        page_offset=input.page_offset,
    )


# =============================================================================
# Workflow Wrappers
# =============================================================================


async def extract_chunk_with_docling(
    chunk_bytes: bytes,
    chunk_index: int,
    total_chunks: int,
    page_offset: int,
    output_prefix: str,
    filename: str,
    project_id: UUID | None = None,
) -> DoclingChunkResult:
    """Workflow wrapper for extract_chunk_with_docling activity."""
    return await workflow.execute_activity(
        _extract_chunk_with_docling,
        ExtractChunkInput(
            chunk_bytes=chunk_bytes,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            page_offset=page_offset,
            output_prefix=output_prefix,
            filename=filename,
            project_id=project_id,
        ),
        start_to_close_timeout=timedelta(minutes=30),
        heartbeat_timeout=timedelta(minutes=2),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_EXTRACTION_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=60),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=300),
        ),
    )
