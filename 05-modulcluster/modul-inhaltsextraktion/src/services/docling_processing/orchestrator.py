# src/services/docling_processing/orchestrator.py
"""
Main orchestrator for Docling PDF extraction pipeline.
"""

import asyncio
import logging
from datetime import timedelta
from pathlib import Path

from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.exceptions import TimeoutError as TemporalTimeoutError

from src.config import get_config
from src.schemas import ExtractionOutput
from src.services.docling_processing.assembly import (
    combine_docling_chunks,
    deduplicate_images,
    upload_debug_files_docling,
)
from src.services.docling_processing.extraction import (
    extract_chunk_with_docling,
)
from src.services.docling_processing.pdf_compression import (
    compress_pdf_images,
    rasterize_chunk,
)
from src.services.docling_processing.pdf_preparation import (
    DoclingActivityInput,
    _sanitize_stem,
    download_and_prepare_pdf,
    split_pdf_for_docling,
)
from src.utils.path_utils import get_output_dir

logger = logging.getLogger(__name__)


def _is_timeout_failure(exc: BaseException) -> bool:
    """Check if an exception represents a Temporal activity timeout.

    Temporal wraps activity timeouts as ActivityError whose .cause is a
    TemporalTimeoutError.  Detecting these lets us skip the raster fallback
    for chunks that timed out -- rasterizing won't help if the document is
    simply too large for docling-serve to handle in time.
    """
    return isinstance(exc, ActivityError) and isinstance(exc.cause, TemporalTimeoutError)


# =============================================================================
# Main Orchestrator
# =============================================================================


async def process_pdf_with_docling(  # noqa: C901
    input: DoclingActivityInput,
) -> ExtractionOutput:
    """
    Process a PDF document with Docling extraction service.

    This function orchestrates the extraction pipeline:
    1. Download and prepare PDF from DMS (via activity)
    2. Compress embedded images to reduce memory pressure (via activity)
    3. Split large PDFs into chunks with adaptive sizing (via activity)
    4. Process each chunk with Docling API (via activity)
    5. Combine results (via activity)
    6. Deduplicate images (via activity)
    7. Upload debug files to DMS (via activity)

    Args:
        input: DoclingActivityInput with file_info and project_id

    Returns:
        ExtractionOutput with markdown, content_list, and image_bytes

    Note:
        This function is called from the workflow thread but all heavy operations
        are delegated to activities to avoid blocking and enable per-step retry.
    """
    filename = input.file_info.filename
    upload_folder = get_output_dir(filename)
    stem = _sanitize_stem(Path(filename).stem)

    workflow.logger.info(f"Starting Docling extraction for: {filename}")

    # Step 1: Download and prepare PDF
    prepared = await download_and_prepare_pdf(input)
    pdf_bytes = prepared.pdf_bytes
    file_size_mb = prepared.file_size_mb

    workflow.logger.info(f"PDF prepared: {prepared.filename} ({file_size_mb:.2f} MB)")

    # Step 2: Compress embedded images (reduces memory pressure on docling-serve)
    compression_result = await compress_pdf_images(pdf_bytes, file_size_mb)
    pdf_bytes = compression_result.pdf_bytes
    file_size_mb = compression_result.file_size_mb

    # Step 3: Split PDF into chunks (if large) with adaptive sizing
    split_result = await split_pdf_for_docling(pdf_bytes, file_size_mb)
    pdf_chunks = split_result.chunks
    page_offsets = split_result.page_offsets

    workflow.logger.info(f"Processing {len(pdf_chunks)} chunk(s)")

    # Step 4: Process chunks with Docling (parallel with semaphore + raster fallback)
    extraction_semaphore = asyncio.Semaphore(get_config().EXTRACTION_CHUNK_CONCURRENCY)
    total_chunks = len(pdf_chunks)

    async def _extract_chunk(i: int, chunk_content: bytes, page_offset: int):
        async with extraction_semaphore:
            return await extract_chunk_with_docling(
                chunk_bytes=chunk_content,
                chunk_index=i,
                total_chunks=total_chunks,
                page_offset=page_offset,
                output_prefix=stem,
                filename=filename,
                project_id=input.project_id,
            )

    # Phase 1: Try all chunks, collecting exceptions instead of failing fast
    raw_results = await asyncio.gather(
        *[_extract_chunk(i, c, p) for i, (c, p) in enumerate(zip(pdf_chunks, page_offsets, strict=False))],
        return_exceptions=True,
    )

    # Phase 2: Separate successes from failures, track timeout vs other errors
    chunk_results = []
    failed_indices: list[int] = []
    timeout_indices: set[int] = set()

    for i, result in enumerate(raw_results):
        if isinstance(result, BaseException):
            workflow.logger.warning(f"Chunk {i + 1}/{total_chunks} failed: {result}")
            failed_indices.append(i)
            if _is_timeout_failure(result):
                timeout_indices.add(i)
        else:
            chunk_results.append(result)

    # Phase 2.5: Sequential retry of non-timeout failures before raster fallback.
    # When concurrency > 1, OOM on docling-serve can cause chunk failures that
    # would succeed if retried one at a time without memory contention.
    cfg = get_config()
    retryable_indices = [i for i in failed_indices if i not in timeout_indices]
    if retryable_indices and cfg.EXTRACTION_CHUNK_CONCURRENCY > 1:
        workflow.logger.info(
            f"Retrying {len(retryable_indices)} failed chunk(s) sequentially "
            f"(was concurrent at N={cfg.EXTRACTION_CHUNK_CONCURRENCY})"
        )
        for i in retryable_indices:
            chunk_num = i + 1
            try:
                workflow.logger.info(
                    f"Retrying chunk {chunk_num}/{total_chunks} sequentially (waiting 10s for docling-serve recovery)"
                )
                await workflow.sleep(timedelta(seconds=10))
                retry_result = await extract_chunk_with_docling(
                    chunk_bytes=pdf_chunks[i],
                    chunk_index=i,
                    total_chunks=total_chunks,
                    page_offset=page_offsets[i],
                    output_prefix=stem,
                    filename=filename,
                    project_id=input.project_id,
                )
                chunk_results.append(retry_result)
                failed_indices.remove(i)
                workflow.logger.info(f"Sequential retry succeeded for chunk {chunk_num}")
            except Exception as retry_err:
                workflow.logger.warning(f"Sequential retry also failed for chunk {chunk_num}: {retry_err}")

    # Phase 3: Apply raster fallback for still-failed chunks (sequentially)
    if failed_indices and cfg.ENABLE_RASTER_FALLBACK:
        workflow.logger.info(
            f"Attempting raster fallback for {len(failed_indices)} failed chunk(s) "
            f"({len(timeout_indices)} timeout(s) will be skipped)"
        )
        for i in failed_indices:
            chunk_num = i + 1

            # Skip raster for oversized chunks -- at 300 DPI rasterization
            # typically increases PDF size, making OOM more likely.
            chunk_size_mb = len(pdf_chunks[i]) / (1024 * 1024)
            if chunk_size_mb > cfg.PDF_TARGET_CHUNK_MB:
                workflow.logger.info(
                    f"Chunk {chunk_num} is {chunk_size_mb:.1f}MB "
                    f"(> {cfg.PDF_TARGET_CHUNK_MB}MB target), "
                    f"skipping raster fallback (would likely increase size)"
                )
                continue

            # Skip raster fallback for timeout failures -- rasterizing won't
            # help if the chunk simply takes too long for docling-serve.
            if i in timeout_indices:
                workflow.logger.info(f"Chunk {chunk_num} failed due to timeout, skipping raster fallback")
                continue

            try:
                # Step 1: Rasterize the problematic chunk
                raster_result = await rasterize_chunk(
                    chunk_bytes=pdf_chunks[i],
                    chunk_index=i,
                    total_chunks=total_chunks,
                )
                workflow.logger.info(
                    f"Rasterized chunk {chunk_num}: "
                    f"{raster_result.original_size_mb:.2f}MB -> "
                    f"{raster_result.rasterized_size_mb:.2f}MB"
                )

                # Step 2: Retry extraction with rasterized bytes
                fallback_result = await extract_chunk_with_docling(
                    chunk_bytes=raster_result.rasterized_bytes,
                    chunk_index=i,
                    total_chunks=total_chunks,
                    page_offset=page_offsets[i],
                    output_prefix=stem,
                    filename=filename,
                    project_id=input.project_id,
                )
                chunk_results.append(fallback_result)
                workflow.logger.info(f"Raster fallback succeeded for chunk {chunk_num}")
            except Exception as fallback_err:
                workflow.logger.warning(f"Raster fallback also failed for chunk {chunk_num}, skipping: {fallback_err}")
    elif failed_indices:
        workflow.logger.warning(f"Raster fallback disabled, skipping {len(failed_indices)} failed chunk(s)")

    # Validate results
    if not chunk_results:
        raise ApplicationError(
            f"All {total_chunks} chunk(s) failed extraction (including raster fallback). Cannot produce output.",
            non_retryable=True,
        )

    if len(chunk_results) < total_chunks:
        workflow.logger.warning(
            f"Partial extraction: {len(chunk_results)}/{total_chunks} chunks succeeded. Output may be incomplete."
        )

    # Sort by page_offset to restore correct page order
    chunk_results.sort(key=lambda r: r.page_offset)

    # Step 5: Combine all chunks in a single activity call.
    # With S3-based refs, each DoclingChunkResult is ~500 bytes (just refs),
    # so passing all chunks at once is well within Temporal's payload limits.
    # The combine activity processes chunks one at a time to bound memory,
    # streams combined data to temp files, and uploads the result to S3.
    combined = await combine_docling_chunks(
        chunk_results,
        project_id=input.project_id,
        filename=filename,
    )
    md_content = combined.md_content
    content_list = combined.content_list
    image_refs = combined.image_refs
    fallback_images = combined.images

    workflow.logger.info(
        f"Combined: {len(content_list)} content items, "
        f"{len(image_refs)} image refs, {len(fallback_images)} fallback images"
    )

    # Step 6: Deduplicate images -- SKIPPED when images were uploaded per-chunk.
    # The downstream filter_enhance step already handles deduplication via
    # perceptual hashing as part of its recurring-element detection pass.
    # Only run dedup when we have fallback image bytes (upload-failed path).
    if fallback_images and not image_refs:
        dedup_result = await deduplicate_images(content_list, fallback_images)
        fallback_images = dedup_result.images
        if dedup_result.duplicate_paths:
            workflow.logger.info(f"Removed {len(dedup_result.duplicate_paths)} duplicate images")
    else:
        workflow.logger.info("Skipping image deduplication (images uploaded per-chunk to DMS)")

    # Step 7: Upload debug files to DMS
    await upload_debug_files_docling(
        content_list=content_list,
        provider_json=combined.provider_json,
        upload_folder=upload_folder,
        stem=stem,
        project_id=input.project_id,
    )

    workflow.logger.info(f"Docling extraction completed for: {filename}")

    return ExtractionOutput(
        markdown=md_content,
        content_list=content_list,
        image_bytes=fallback_images,
        image_refs=image_refs,
    )
