# src/activities/extraction.py
"""
Temporal activities for document extraction using provider abstraction.

This module provides extraction activities using the configured provider.

Note: For primary extraction, use src/services/docling_processing.py instead.
This module's extract_document_direct() is kept as a simpler fallback path.

Architecture (External pattern):
- Returns data directly (markdown, content_list, image_bytes) via Temporal codec
- Images are returned as raw bytes; DMS upload happens in filter_enhance
- Debugging files (markdown, content_list JSON) optionally uploaded to DMS
- Result is compatible with ExtractionOutput for seamless provider switching

Usage:
    # In workflow - works the same for both providers:
    result = await extract_document_direct(
        ExtractDocumentInput(file_info=file_info, project_id=project_id)
    )
    # result.markdown is string, result.content_list is list, result.image_bytes is Dict[str, bytes]
"""

import json
import logging
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.activities.dms_activities import DmsFileInfo
from src.config import get_config
from src.env import ENV
from src.processors.filter import HeaderFooterFilter
from src.processors.preprocessor import Preprocessor
from src.providers.docling_provider import DoclingProvider
from src.schemas import ExtractionOutput
from src.utils.dms_utils import (
    DmsUploadInput,
    download_file,
)
from src.utils.dms_utils import (
    upload_file as dms_upload_file,
)
from src.utils.path_utils import get_output_dir

logger = logging.getLogger(__name__)


class ExtractDocumentInput(BaseModel):
    """Input for direct extraction activity."""

    file_info: DmsFileInfo
    project_id: UUID


def _sanitize_stem(stem: str) -> str:
    """
    Sanitize stem to handle problematic Unicode characters from DMS filenames.

    DMS filenames may contain decomposed Unicode (U + combining diaeresis instead of Ü)
    or invisible line separators (U+2028, U+2029) that corrupt filenames.
    """
    import unicodedata

    original_stem = stem
    stem = unicodedata.normalize("NFC", stem)  # Compose decomposed chars
    # Remove control chars, format chars, and line/paragraph separators
    stem = "".join(c for c in stem if unicodedata.category(c) not in {"Cc", "Cf", "Zl", "Zp"} or c in (" ", "\t"))
    stem = stem.replace("\u2028", "_").replace("\u2029", "_")
    stem = stem.replace("\n", "_").replace("\r", "_")
    if stem != original_stem:
        activity.logger.info(f"Sanitized stem: {len(original_stem)} -> {len(stem)} chars")
    return stem


# --- Direct Activity (External pattern) ---


@activity.defn(name="extract_document_direct")
async def _extract_document_direct(input: ExtractDocumentInput) -> ExtractionOutput:
    """
    Extract content from a PDF using the configured provider.

    This activity follows the External pattern:
    - Downloads the file from DMS and converts to PDF if needed
    - Returns markdown, content_list, and raw image_bytes
    - Image DMS upload is deferred to filter_enhance (only surviving images get uploaded)

    Args:
        input: ExtractDocumentInput with file_info (DmsFileInfo), project_id

    Returns:
        ExtractionOutput with markdown (str), content_list (list), image_bytes (Dict[str, bytes])
    """
    filename = input.file_info.filename
    doc_stem = get_output_dir(filename)
    stem = _sanitize_stem(Path(filename).stem)

    activity.logger.info(f"Starting extraction for {stem} using provider: {ENV.EXTRACTION_PROVIDER}")

    # Download file from DMS and convert to PDF if needed
    file_bytes = await download_file(input.file_info.file_id)
    pdf_bytes, _ = await Preprocessor.convert_to_pdf_if_needed(filename, file_bytes)

    file_size_mb = len(pdf_bytes) / (1024 * 1024)
    activity.logger.info(f"PDF size: {file_size_mb:.2f} MB")

    result = await DoclingProvider.extract(pdf_bytes, filename, stem)

    activity.logger.info(f"Extraction completed: {len(result.content_list)} items, {len(result.images)} images")

    # Filter duplicate images before uploading to DMS
    # This avoids uploading duplicates and eliminates DMS round-trips for dedup in postprocessing
    duplicate_img_paths = HeaderFooterFilter.find_duplicate_images(result.content_list, result.images)
    if duplicate_img_paths:
        original_count = len(result.images)
        result.images = {
            k: v
            for k, v in result.images.items()
            if k not in duplicate_img_paths and f"images/{k}" not in duplicate_img_paths
        }
        activity.logger.info(
            f"Image dedup: {original_count} -> {len(result.images)} images "
            f"({len(duplicate_img_paths)} duplicates removed before DMS upload)"
        )

    # Upload debugging files to DMS (optional, for inspection)
    # Main markdown file
    await dms_upload_file(
        DmsUploadInput(
            data=result.md_content.encode("utf-8"),
            filename=f"{doc_stem}/{stem}.md",
            project_id=input.project_id,
            file_type="content_extraction",
            content_type="text/markdown",
        )
    )

    # Original provider markdown for comparison (if available)
    if result.original_md_content:
        await dms_upload_file(
            DmsUploadInput(
                data=result.original_md_content.encode("utf-8"),
                filename=f"{doc_stem}/{stem}_docling.md",
                project_id=input.project_id,
                file_type="content_extraction",
                content_type="text/markdown",
            )
        )

    # Raw provider JSON for debugging (if available)
    if result.provider_json:
        provider_json_str = json.dumps(result.provider_json, ensure_ascii=False, indent=2)
        await dms_upload_file(
            DmsUploadInput(
                data=provider_json_str.encode("utf-8"),
                filename=f"{doc_stem}/{stem}_docling.json",
                project_id=input.project_id,
                file_type="content_extraction",
                content_type="application/json",
            )
        )

    # Content list JSON for debugging
    content_list_json = json.dumps(result.content_list, ensure_ascii=False, indent=2)
    await dms_upload_file(
        DmsUploadInput(
            data=content_list_json.encode("utf-8"),
            filename=f"{doc_stem}/{stem}_content_list.json",
            project_id=input.project_id,
            file_type="content_extraction",
            content_type="application/json",
        )
    )

    activity.logger.info(f"Extraction completed for {stem}")

    return ExtractionOutput(
        markdown=result.md_content,
        content_list=result.content_list,
        image_bytes=result.images,
    )


async def extract_document_direct(input: ExtractDocumentInput) -> ExtractionOutput:
    """
    Workflow wrapper for direct extraction (External pattern).

    Downloads the file from DMS internally to avoid serializing large PDF bytes
    in the workflow thread (which would exceed Temporal's 2s yield deadline).

    Args:
        input: ExtractDocumentInput with file_info (DmsFileInfo), project_id

    Returns:
        ExtractionOutput with markdown (str), content_list (list), image_bytes (Dict[str, bytes])
    """
    return await workflow.execute_activity(
        _extract_document_direct,
        input,
        start_to_close_timeout=timedelta(minutes=45),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_LLM_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=10),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=120),
        ),
    )
