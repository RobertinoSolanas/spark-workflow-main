# src/services/docling_processing/pdf_preparation.py
"""
PDF download, validation, conversion, and splitting activities.
"""

import io
import logging
from datetime import timedelta
from uuid import UUID

import pypdfium2 as pdfium
from pydantic import BaseModel
from temporal import Base64Bytes
from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

from src.activities.dms_activities import DmsFileInfo
from src.config import get_config
from src.processors.preprocessor import NotValidPdfError, Preprocessor
from src.utils.dms_utils import download_file

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic I/O Models
# =============================================================================


class DoclingActivityInput(BaseModel):
    """Input for the Docling extraction orchestrator."""

    file_info: DmsFileInfo
    project_id: UUID


class PreparedPdfOutput(BaseModel):
    """Output from download_and_prepare_pdf activity."""

    pdf_bytes: Base64Bytes
    filename: str
    file_size_mb: float


class SplitPdfForDoclingInput(BaseModel):
    """Input for split_pdf_for_docling activity."""

    pdf_bytes: Base64Bytes
    file_size_mb: float


class SplitPdfForDoclingOutput(BaseModel):
    """Output from split_pdf_for_docling activity."""

    chunks: list[Base64Bytes]
    page_offsets: list[int]  # Starting page number for each chunk


# =============================================================================
# Helpers
# =============================================================================


def _sanitize_stem(stem: str) -> str:
    """
    Sanitize stem to handle problematic Unicode characters from DMS filenames.

    DMS filenames may contain decomposed Unicode (U + combining diaeresis instead of U)
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


# =============================================================================
# Activity Definitions
# =============================================================================


@activity.defn(name="download_and_prepare_pdf_docling")
async def _download_and_prepare_pdf(input: DoclingActivityInput) -> PreparedPdfOutput:
    """
    Download file from DMS and convert to PDF if needed.

    This activity handles:
    - DMS download using file_id
    - PDF validation
    - Conversion of non-PDF documents (via LibreOffice/unoserver)

    Args:
        input: DoclingActivityInput with file_info and project_id

    Returns:
        PreparedPdfOutput with PDF bytes, filename, and size
    """
    filename = input.file_info.filename
    activity.logger.info(f"Downloading and preparing PDF: {filename}")

    # Download file from DMS
    file_bytes = await download_file(input.file_info.file_id)
    activity.logger.info(f"Downloaded {len(file_bytes)} bytes from DMS")

    # Validate and convert if needed
    try:
        await Preprocessor.validate_pdf(file_bytes)
        pdf_bytes = file_bytes
    except NotValidPdfError:
        activity.logger.info(f"Not a valid PDF, converting: {filename}")
        pdf_bytes, filename = await Preprocessor.convert_to_pdf_if_needed(filename, file_bytes)

    file_size_mb = len(pdf_bytes) / (1024 * 1024)
    activity.logger.info(f"PDF prepared: {filename} ({file_size_mb:.2f} MB)")

    return PreparedPdfOutput(
        pdf_bytes=pdf_bytes,
        filename=filename,
        file_size_mb=file_size_mb,
    )


@activity.defn(name="split_pdf_for_docling")
async def _split_pdf_for_docling(
    input: SplitPdfForDoclingInput,
) -> SplitPdfForDoclingOutput:
    """
    Split large PDF into chunks using pypdfium2 with adaptive sizing.

    Two-phase logic:
    - PDFs < PDF_FORCE_SPLIT_THRESHOLD_MB (40MB default) are never split
    - PDFs >= threshold are always split with adaptive chunk sizing

    Adaptive formula:
        chunk_size = min(PDF_PAGE_CHUNK_SIZE, max(1, int(TARGET / avg_mb_per_page)))

    Args:
        input: SplitPdfForDoclingInput with pdf_bytes and file_size_mb

    Returns:
        SplitPdfForDoclingOutput with list of chunk bytes and page offsets
    """
    pdf_bytes = input.pdf_bytes
    file_size_mb = input.file_size_mb

    cfg = get_config()

    # Fast path: small PDFs never need splitting
    if file_size_mb < cfg.PDF_FORCE_SPLIT_THRESHOLD_MB:
        activity.logger.info(
            f"PDF size {file_size_mb:.2f}MB < {cfg.PDF_FORCE_SPLIT_THRESHOLD_MB}MB, skipping split (fast path)"
        )
        return SplitPdfForDoclingOutput(chunks=[pdf_bytes], page_offsets=[0])

    # Open PDF to get page count for adaptive chunk sizing
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        num_pages = len(pdf)
        avg_mb_per_page = file_size_mb / max(num_pages, 1)

        activity.logger.info(f"PDF stats: {file_size_mb:.2f}MB, {num_pages} pages, {avg_mb_per_page:.2f} MB/page")

        # Adaptive chunk size: target PDF_TARGET_CHUNK_MB per chunk
        adaptive_size = max(1, int(cfg.PDF_TARGET_CHUNK_MB / avg_mb_per_page))
        chunk_size = min(cfg.PDF_PAGE_CHUNK_SIZE, adaptive_size)

        activity.logger.info(
            f"Splitting PDF into chunks of {chunk_size} pages (adaptive={adaptive_size}, cap={cfg.PDF_PAGE_CHUNK_SIZE})"
        )

        chunks: list[bytes] = []
        page_offsets: list[int] = []

        for start_page in range(0, num_pages, chunk_size):
            end_page = min(start_page + chunk_size, num_pages)

            chunk_pdf = pdfium.PdfDocument.new()
            chunk_pdf.import_pages(pdf, pages=range(start_page, end_page))
            buffer = io.BytesIO()
            chunk_pdf.save(buffer, version=17)
            chunk_pdf.close()

            chunk_data = buffer.getvalue()
            if not chunk_data:
                activity.logger.warning(f"Chunk for pages {start_page}-{end_page - 1} produced empty bytes, skipping")
                continue
            chunks.append(chunk_data)
            page_offsets.append(start_page)

        if not chunks:
            raise ApplicationError(
                f"All chunks produced empty bytes from PDF ({num_pages} pages). "
                f"The PDF may be corrupted or unreadable.",
                non_retryable=True,
            )

        activity.logger.info(f"Split PDF into {len(chunks)} chunks covering {num_pages} pages")
    finally:
        pdf.close()

    return SplitPdfForDoclingOutput(chunks=chunks, page_offsets=page_offsets)


# =============================================================================
# Workflow Wrappers
# =============================================================================


async def download_and_prepare_pdf(input: DoclingActivityInput) -> PreparedPdfOutput:
    """Workflow wrapper for download_and_prepare_pdf activity."""
    return await workflow.execute_activity(
        _download_and_prepare_pdf,
        input,
        start_to_close_timeout=timedelta(minutes=10),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_STORAGE_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=60),
        ),
    )


async def split_pdf_for_docling(
    pdf_bytes: bytes,
    file_size_mb: float,
) -> SplitPdfForDoclingOutput:
    """Workflow wrapper for split_pdf_for_docling activity."""
    return await workflow.execute_activity(
        _split_pdf_for_docling,
        SplitPdfForDoclingInput(pdf_bytes=pdf_bytes, file_size_mb=file_size_mb),
        start_to_close_timeout=timedelta(minutes=10),
        retry_policy=RetryPolicy(maximum_attempts=get_config().TEMPORAL_PROCESSING_ACTIVITY_MAX_ATTEMPTS),
    )
