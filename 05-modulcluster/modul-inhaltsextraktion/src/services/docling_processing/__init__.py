# src/services/docling_processing/__init__.py
"""
Temporal activities and orchestrator for Docling PDF extraction.

This package provides separate activities for each step, enabling better reliability,
retryability, and performance with large documents.

Architecture:
    process_pdf_with_docling() - Orchestrator function (called from workflow)
        |
        +-- 1. download_and_prepare_pdf()     [10min, 3 retries]
        |       +-- DMS download + PDF conversion
        |
        +-- 2. split_pdf_for_docling()        [10min, 2 retries]
        |       +-- pypdfium2 splitting (reuse existing logic)
        |
        +-- 3. FOR EACH chunk:
        |   +-- extract_chunk_with_docling()  [30min, 2 retries]
        |           +-- Call docling-serve API + process results
        |
        +-- 4. combine_docling_chunks()       [15min, 2 retries]
        |       +-- Merge all chunk results (inline, codec-offloaded)
        |
        +-- 5. deduplicate_images()           [10min, 2 retries]
        |       +-- Perceptual hash deduplication (CPU-intensive)
        |
        +-- 6. upload_debug_files_docling()   [10min, 3 retries]
                +-- Upload JSON debug files to DMS
"""

# --- pdf_preparation ---
# --- assembly ---
from src.services.docling_processing.assembly import (
    CombineDoclingChunksInput,
    CombineDoclingChunksOutput,
    DeduplicateImagesInput,
    DeduplicateImagesOutput,
    UploadDebugFilesDoclingInput,
    _combine_docling_chunks,
    _deduplicate_images,
    _upload_debug_files_docling,
    combine_docling_chunks,
    deduplicate_images,
    upload_debug_files_docling,
)

# --- extraction ---
from src.services.docling_processing.extraction import (
    DoclingChunkResult,
    ExtractChunkInput,
    _extract_chunk_with_docling,
    extract_chunk_with_docling,
)

# --- orchestrator ---
from src.services.docling_processing.orchestrator import (
    _is_timeout_failure,
    process_pdf_with_docling,
)

# --- pdf_compression ---
from src.services.docling_processing.pdf_compression import (
    CompressPdfImagesInput,
    CompressPdfImagesOutput,
    RasterizeChunkInput,
    RasterizeChunkOutput,
    _compress_pdf_images,
    _rasterize_chunk,
    compress_pdf_images,
    rasterize_chunk,
)
from src.services.docling_processing.pdf_preparation import (
    DoclingActivityInput,
    PreparedPdfOutput,
    SplitPdfForDoclingInput,
    SplitPdfForDoclingOutput,
    _download_and_prepare_pdf,
    _sanitize_stem,
    _split_pdf_for_docling,
    download_and_prepare_pdf,
    split_pdf_for_docling,
)

__all__ = [
    # pdf_preparation
    "DoclingActivityInput",
    "PreparedPdfOutput",
    "SplitPdfForDoclingInput",
    "SplitPdfForDoclingOutput",
    "_download_and_prepare_pdf",
    "_sanitize_stem",
    "_split_pdf_for_docling",
    "download_and_prepare_pdf",
    "split_pdf_for_docling",
    # pdf_compression
    "CompressPdfImagesInput",
    "CompressPdfImagesOutput",
    "RasterizeChunkInput",
    "RasterizeChunkOutput",
    "_compress_pdf_images",
    "_rasterize_chunk",
    "compress_pdf_images",
    "rasterize_chunk",
    # extraction
    "DoclingChunkResult",
    "ExtractChunkInput",
    "_extract_chunk_with_docling",
    "extract_chunk_with_docling",
    # assembly
    "CombineDoclingChunksInput",
    "CombineDoclingChunksOutput",
    "DeduplicateImagesInput",
    "DeduplicateImagesOutput",
    "UploadDebugFilesDoclingInput",
    "_combine_docling_chunks",
    "_deduplicate_images",
    "_upload_debug_files_docling",
    "combine_docling_chunks",
    "deduplicate_images",
    "upload_debug_files_docling",
    # orchestrator
    "_is_timeout_failure",
    "process_pdf_with_docling",
]
