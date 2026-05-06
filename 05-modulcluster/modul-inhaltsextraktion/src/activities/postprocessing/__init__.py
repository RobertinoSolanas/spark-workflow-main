# src/activities/postprocessing/__init__.py
"""
Temporal activities for post-processing steps like filtering, chunking, and final assembly.

Re-exports all public names so existing imports continue to work.
"""

from src.activities.postprocessing.chunking import (
    ChunkMarkdownInput,
    SplitMarkdownByPagesInput,
    _chunk_markdown,
    _split_markdown_by_pages,
    chunk_markdown,
    split_markdown_by_pages,
)
from src.activities.postprocessing.dms_upload import (
    AssembleFinalJsonResult,
    CreateFinalJsonInput,
    CreateSummaryFromResultsInput,
    SummaryResult,
    UploadImagesToDmsInput,
    _create_final_json,
    _create_summary_from_results,
    _upload_image_to_dms,
    _upload_images_to_dms,
    create_final_json,
    create_summary_from_results,
    upload_images_to_dms,
)
from src.activities.postprocessing.filtering import (
    FilterEnhanceInput,
    FilterEnhanceResult,
    _filter_enhance_content,
    filter_enhance,
)
from src.activities.postprocessing.vlm_preparation import (
    _prepare_vlm_inputs_activity,
    prepare_vlm_inputs_wrapper,
)

__all__ = [
    # filtering
    "FilterEnhanceInput",
    "FilterEnhanceResult",
    "_filter_enhance_content",
    "filter_enhance",
    # chunking
    "ChunkMarkdownInput",
    "SplitMarkdownByPagesInput",
    "_chunk_markdown",
    "_split_markdown_by_pages",
    "chunk_markdown",
    "split_markdown_by_pages",
    # dms_upload
    "UploadImagesToDmsInput",
    "CreateFinalJsonInput",
    "AssembleFinalJsonResult",
    "SummaryResult",
    "CreateSummaryFromResultsInput",
    "_upload_image_to_dms",
    "_upload_images_to_dms",
    "_create_final_json",
    "_create_summary_from_results",
    "upload_images_to_dms",
    "create_final_json",
    "create_summary_from_results",
    # vlm_preparation
    "_prepare_vlm_inputs_activity",
    "prepare_vlm_inputs_wrapper",
]
