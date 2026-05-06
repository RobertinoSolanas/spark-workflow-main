# src/activities/postprocessing/filtering.py
"""
Temporal activities for content filtering and enhancement.
"""

import asyncio
import re
import time
from datetime import timedelta
from uuid import UUID

from pydantic import BaseModel
from temporal import Base64Bytes
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.config import get_config
from src.processors.enhancer import MarkdownEnhancer
from src.processors.filter import HeaderFooterFilter
from src.providers.base import ContentItemDict
from src.schemas import ExtractionOutput
from src.utils.dms_utils import download_file
from src.utils.path_utils import get_output_dir


class FilterEnhanceInput(BaseModel):
    """Input for filter_enhance_content activity."""

    markdown: str = ""
    content_list: list[ContentItemDict] = []
    image_bytes: dict[str, Base64Bytes] = {}
    image_refs: dict[str, str] = {}  # filename -> DMS file_id (per-chunk upload path)
    project_id: UUID
    filename: str


class FilterEnhanceResult(BaseModel):
    """Output from filter_enhance_content containing filtered markdown, content list, and image data."""

    markdown: str
    content_list: list[ContentItemDict]
    images: dict[str, Base64Bytes]
    image_refs: dict[str, str] = {}  # filename -> DMS file_id (when uploaded in filter_enhance)


# Import here to avoid circular dependency at module level
from src.activities.postprocessing.dms_upload import _upload_image_to_dms  # noqa: E402


@activity.defn(name="filter_enhance_content")
async def _filter_enhance_content(  # noqa: C901
    input: FilterEnhanceInput,
) -> FilterEnhanceResult:
    """
    Filter headers/footers, enhance markdown with page numbers.

    Returns surviving image bytes for downstream VLM processing.
    Images are uploaded to DMS separately via upload_images_to_dms.

    Uses two filtering passes:
    1. Label-based (for Docling): Uses provider's page_header/page_footer labels
    2. Recurring element detection: Catches unlabeled headers/footers + duplicate images

    Provider-specific handling:
    - Docling: Skip text filtering (already done during markdown generation)
    """
    image_bytes_dict = dict(input.image_bytes)
    content_list = input.content_list
    md_content = input.markdown

    # If images were uploaded per-chunk to DMS (image_refs populated),
    # download any that aren't already in image_bytes_dict so the existing
    # filtering logic can operate on bytes.  This handles both the pure
    # per-chunk path (image_bytes empty) and the mixed case where some
    # chunks exceeded the upload threshold and others didn't.
    refs_to_download: dict[str, str] = (
        {k: v for k, v in input.image_refs.items() if k not in image_bytes_dict} if input.image_refs else {}
    )

    if refs_to_download:
        activity.logger.info(f"Downloading {len(refs_to_download)} images from DMS (per-chunk upload path)")
        dl_semaphore = asyncio.Semaphore(get_config().MAX_CONCURRENT_DMS_IMAGE_UPLOADS)
        dl_count = 0

        async def _download_image(img_name: str, file_id: str) -> None:
            nonlocal dl_count
            async with dl_semaphore:
                try:
                    img_data = await download_file(file_id)
                    image_bytes_dict[img_name] = img_data
                    dl_count += 1
                    activity.heartbeat(f"Downloaded {dl_count}/{len(refs_to_download)} images")
                except Exception as e:
                    activity.logger.warning(f"Failed to download image {img_name} (file_id={file_id}): {e}")

        await asyncio.gather(*[_download_image(name, fid) for name, fid in refs_to_download.items()])
        activity.logger.info(f"Downloaded {dl_count}/{len(refs_to_download)} images from DMS")

    # Collect all filtered elements across both passes
    images_to_filter: set[str] = set()
    html_tables_to_filter: set[str] = set()
    text_to_filter: set[str] = set()

    # First pass: Filter by provider labels (if available, e.g., Docling)
    if get_config().TRUST_PROVIDER_LABELS_FOR_FILTER:
        (
            content_list,
            label_images,
            label_tables,
            label_text,
        ) = HeaderFooterFilter.filter_by_provider_labels(content_list)
        images_to_filter.update(label_images)
        html_tables_to_filter.update(label_tables)
        text_to_filter.update(label_text)

    # Second pass: Filter recurring elements (catches unlabeled headers/footers + duplicate images)
    # Run synchronously - asyncio.to_thread not available in activity context
    (
        filtered_content_list,
        recurring_images,
        recurring_tables,
        recurring_text,
    ) = HeaderFooterFilter.filter_recurring_elements(
        content_list,
        image_bytes_dict,
        page_height=get_config().PAGE_HEIGHT_POINTS,
    )
    images_to_filter.update(recurring_images)
    html_tables_to_filter.update(recurring_tables)
    text_to_filter.update(recurring_text)

    # Insert page numbers (skip if already present from Docling provider)
    if '<seite nummer="' not in md_content:
        md_content = MarkdownEnhancer.insert_page_numbers(md_content, filtered_content_list)

    # Remove filtered images from markdown and image_bytes dict
    if images_to_filter:
        bare_names = set()
        for img_path in images_to_filter:
            # Normalize: strip "images/" prefix if present to avoid double-prefix in regex.
            # Content list may store "images/file.png" or "file.png".
            bare_name = img_path.removeprefix("images/")
            bare_names.add(bare_name)
            image_bytes_dict.pop(img_path, None)
            image_bytes_dict.pop(bare_name, None)

        # Build a single combined regex for all filtered image names
        escaped_names = "|".join(re.escape(name) for name in bare_names)
        combined_pattern = re.compile(
            rf"(?:"
            rf"!\[.*?\]\(images/(?:{escaped_names})\)"
            rf"|<(?:BILD|TABELLE) img_path=\"images/(?:{escaped_names})\"[^>]*/>\n*"
            rf"|<BILD[^>]*img_path=\"images/(?:{escaped_names})\"[^>]*>.*?</BILD>\n*"
            rf"|<TABELLE[^>]*img_path=\"images/(?:{escaped_names})\"[^>]*>.*?</TABELLE>\n*"
            rf")",
            re.DOTALL,
        )
        t0 = time.monotonic()
        md_content = combined_pattern.sub("", md_content)
        duration_ms = (time.monotonic() - t0) * 1000
        activity.logger.info(
            f"Image filter regex took {duration_ms:.1f}ms ({len(bare_names)} patterns, {len(md_content)} chars)"
        )

    # Remove filtered tables
    for html_table in html_tables_to_filter:
        md_content = md_content.replace(html_table, "")

    activity.logger.info(f"{len(image_bytes_dict)} surviving images (filtered out {len(images_to_filter)} images)")

    # Safety net: remove any remaining markdown image refs that have no uploaded file.
    # This catches images that were in the markdown but never in image_bytes_dict
    # (e.g., extraction produced a reference but failed to extract the image bytes).
    orphaned = re.findall(r"!\[.*?\]\(images/([^)]+)\)", md_content)
    removed_orphans = 0
    for orphan_filename in orphaned:
        if orphan_filename not in image_bytes_dict:
            md_content = re.sub(rf"!\[.*?\]\(images/{re.escape(orphan_filename)}\)", "", md_content)
            removed_orphans += 1
    if removed_orphans:
        activity.logger.info(f"Removed {removed_orphans} orphaned image references from markdown")

    # Upload surviving images to DMS directly (avoids carrying image bytes
    # through subsequent activity boundaries — saves ~600MB of S3 I/O for 200 images)
    #
    # Optimization: for the >100MB per-chunk upload path, images were already
    # uploaded to DMS during extraction. Reuse those refs for surviving images
    # instead of re-uploading. Only upload images without an existing ref.
    image_refs: dict[str, str] = {}
    images_to_upload: dict[str, bytes] = {}
    existing_refs = input.image_refs

    for img_name, img_data in image_bytes_dict.items():
        if img_name in existing_refs:
            image_refs[img_name] = existing_refs[img_name]
        else:
            images_to_upload[img_name] = img_data

    if existing_refs:
        activity.logger.info(
            f"Reusing {len(image_refs)} existing DMS refs from extraction, "
            f"{len(images_to_upload)} images need uploading"
        )

    upload_folder = get_output_dir(input.filename)
    semaphore = asyncio.Semaphore(get_config().MAX_CONCURRENT_DMS_IMAGE_UPLOADS)
    uploaded_count = 0
    total_images = len(images_to_upload)

    async def _do_upload(name: str, data: bytes) -> None:
        nonlocal uploaded_count
        file_obj = await _upload_image_to_dms(
            name,
            data,
            semaphore=semaphore,
            upload_folder=upload_folder,
            project_id=input.project_id,
        )
        if file_obj:
            image_refs[name] = str(file_obj.id)
            uploaded_count += 1
            activity.heartbeat(f"Uploaded {uploaded_count}/{total_images} images")

    if images_to_upload:
        await asyncio.gather(*[_do_upload(name, data) for name, data in images_to_upload.items()])
    activity.logger.info(f"Uploaded {uploaded_count}/{total_images} images to DMS in filter_enhance")

    return FilterEnhanceResult(
        markdown=md_content,
        content_list=filtered_content_list,
        images=image_bytes_dict,
        image_refs=image_refs,
    )


async def filter_enhance(
    extraction_result: ExtractionOutput,
    project_id: UUID,
    filename: str,
) -> FilterEnhanceResult:
    """Workflow wrapper for filter_enhance_content activity."""
    return await workflow.execute_activity(
        _filter_enhance_content,
        FilterEnhanceInput(
            markdown=extraction_result.markdown,
            content_list=extraction_result.content_list,
            image_bytes=extraction_result.image_bytes,
            image_refs=extraction_result.image_refs,
            project_id=project_id,
            filename=filename,
        ),
        start_to_close_timeout=timedelta(minutes=30),
        heartbeat_timeout=timedelta(minutes=2),
        retry_policy=RetryPolicy(maximum_attempts=get_config().TEMPORAL_PROCESSING_ACTIVITY_MAX_ATTEMPTS),
    )
