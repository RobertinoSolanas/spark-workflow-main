# src/workflows/helpers/vlm_batch_processor.py
"""
Two-phase VLM processing helper for SingleDocumentWorkflow.

Phase 1 — Extract + Describe (VLM, needs image bytes):
  Semaphore-gated child workflows, returning ``VLMExtractDescribeOutput``.

Phase 2 — Summarize + Assemble (LLM, text-only):
  Concurrent ``summarize_visual_element`` activities over all intermediates,
  followed by pure-Python assembly into ``VLMWorkflowOutput``.

The public entry point ``process_vlm_batches`` keeps the same signature and
return type so that ``SingleDocumentWorkflow`` is unaffected.
"""

import asyncio
from datetime import timedelta

from temporalio import workflow

from src.activities.vlm_processing import (
    SummarizeVisualElementInput,
    summarize_visual_element,
)
from src.config import get_config
from src.utils.text_utils import clean_vlm_output, fix_utf8_mojibake
from src.workflows.vlm_enhancement.output_format import (
    VlmAnalysis,
    VLMExtractDescribeOutput,
    VLMWorkflowInput,
    VLMWorkflowOutput,
)
from src.workflows.vlm_enhancement.workflow import VLMWorkflow

# ---------------------------------------------------------------------------
# Phase 1: Extract + Describe (VLM child workflows)
# ---------------------------------------------------------------------------


async def _run_extract_describe(
    vlm_inputs: list[VLMWorkflowInput],
) -> list[VLMExtractDescribeOutput]:
    """Launch VLM child workflows with a semaphore concurrency cap."""
    cfg = get_config()
    batch_size = cfg.TEMPORAL_VLM_CHILD_WORKFLOW_BATCH_SIZE
    total = len(vlm_inputs)
    workflow.logger.info(f"Phase 1: Launching {total} VLM extract+describe workflows (concurrency {batch_size})")

    semaphore = asyncio.Semaphore(batch_size)

    async def run_one(vlm_input: VLMWorkflowInput) -> VLMExtractDescribeOutput:
        async with semaphore:
            return await workflow.execute_child_workflow(
                VLMWorkflow.run,
                vlm_input,
                id=f"vlm-enhancement-{vlm_input.image_ref.replace('/', '-')}",
                task_queue=workflow.info().task_queue,
                task_timeout=timedelta(seconds=60),
            )

    results = await asyncio.gather(*[run_one(inp) for inp in vlm_inputs], return_exceptions=True)

    intermediates: list[VLMExtractDescribeOutput] = []
    failed_count = 0
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            workflow.logger.error(f"VLM extract+describe failed for {vlm_inputs[i].image_ref}: {result}")
            failed_count += 1
        else:
            intermediates.append(result)

    workflow.logger.info(
        f"Phase 1 complete: {len(intermediates)}/{total} succeeded"
        + (f" ({failed_count} failed)" if failed_count else "")
    )
    max_tolerated = max(1, int(total * cfg.VLM_FAILURE_TOLERANCE))
    if failed_count > max_tolerated:
        raise RuntimeError(
            f"VLM extract+describe failed for {failed_count}/{total} elements (tolerance: {max_tolerated})"
        )
    elif failed_count > 0:
        workflow.logger.warning(
            f"VLM: {failed_count}/{total} extract+describe elements failed "
            f"(within tolerance of {max_tolerated}), proceeding with partial results"
        )
    return intermediates


# ---------------------------------------------------------------------------
# Phase 2: Summarize + Assemble (LLM activities, text-only)
# ---------------------------------------------------------------------------


def _assemble_vlm_output(
    intermediate: VLMExtractDescribeOutput,
    analysis: VlmAnalysis,
) -> VLMWorkflowOutput:
    """Pure-Python assembly of the final VLMWorkflowOutput.

    Applies hallucination flag resolution, text cleanup, and XML block
    construction — logic previously in ``VLMWorkflow.run``.
    """
    # Determine if extraction/description should be removed.
    #
    # Extraction hallucination: use ONLY size/pattern-based detection.
    # The LLM judge cannot verify OCR output because it doesn't see the image.
    # Pre-extracted HTML (Docling tables) is structural and never flagged.
    #
    # Description hallucination: use both LLM and size-based detection.
    has_pre_extracted_html = intermediate.element_type == "table" and intermediate.raw_html
    extraction_is_bad = not has_pre_extracted_html and intermediate.extraction_hallucinated_by_size
    description_is_bad = analysis.description_is_hallucinated or intermediate.description_hallucinated_by_size

    final_extraction = (
        "[Content removed due to potential hallucination]"
        if extraction_is_bad
        else clean_vlm_output(fix_utf8_mojibake(intermediate.extraction_result))
    )
    final_description = (
        "[Description removed due to potential hallucination]"
        if description_is_bad
        else clean_vlm_output(fix_utf8_mojibake(intermediate.description_result))
    )
    final_summary = clean_vlm_output(fix_utf8_mojibake(analysis.summary))

    caption_tag = f"\n<caption_text>{analysis.caption}</caption_text>" if analysis.caption else ""
    footnote_tag = f"\n<footnote_text>{analysis.footnote}</footnote_text>" if analysis.footnote else ""

    if final_extraction.strip().lower().startswith("<table>") or intermediate.element_type == "table":
        replacement_block = (
            f'\n\n<TABELLE img_path="{intermediate.image_ref}">'
            f"{caption_tag}\n"
            f"<content>\n{final_extraction}\n</content>\n"
            f"<description>\n{final_description}\n</description>\n"
            f"<summary>\n{final_summary}\n</summary>"
            f"{footnote_tag}\n"
            f"</TABELLE>"
        )
    else:
        replacement_block = (
            f'\n\n<BILD img_path="{intermediate.image_ref}">'
            f"{caption_tag}\n"
            f"<content>\n{final_extraction}\n</content>\n"
            f"<description>\n{final_description}\n</description>\n"
            f"<summary>\n{final_summary}\n</summary>"
            f"{footnote_tag}\n"
            f"</BILD>"
        )

    return VLMWorkflowOutput(
        original_content=intermediate.full_tag or "",
        replacement_block=replacement_block,
    )


async def _summarize_and_assemble(
    intermediates: list[VLMExtractDescribeOutput],
) -> list[VLMWorkflowOutput]:
    """Run summary activities with a semaphore cap, then assemble final outputs."""
    cfg = get_config()
    total = len(intermediates)
    batch_size = cfg.TEMPORAL_VLM_CHILD_WORKFLOW_BATCH_SIZE
    workflow.logger.info(f"Phase 2: Summarizing {total} visual elements (concurrency {batch_size})")

    # Truncate extraction_result and description_result for the summary LLM —
    # the full content is only needed in the final assembled output, not for
    # generating the summary.  Keeps each call fast on ministral-8b.
    ext_max = cfg.VLM_SUMMARY_EXTRACTION_MAX_CHARS
    desc_max = cfg.VLM_SUMMARY_DESCRIPTION_MAX_CHARS
    semaphore = asyncio.Semaphore(batch_size)

    async def _summarize_one(inter: VLMExtractDescribeOutput) -> VlmAnalysis:
        async with semaphore:
            return await summarize_visual_element(
                SummarizeVisualElementInput(
                    context_text=inter.context_text,
                    extraction_result=inter.extraction_result[:ext_max]
                    if len(inter.extraction_result) > ext_max
                    else inter.extraction_result,
                    description_result=inter.description_result[:desc_max]
                    if len(inter.description_result) > desc_max
                    else inter.description_result,
                )
            )

    analyses = await asyncio.gather(*[_summarize_one(inter) for inter in intermediates], return_exceptions=True)

    vlm_results: list[VLMWorkflowOutput] = []
    failed_count = 0
    for i, analysis in enumerate(analyses):
        if isinstance(analysis, BaseException):
            workflow.logger.error(f"VLM summary failed for {intermediates[i].image_ref}: {analysis}")
            failed_count += 1
        else:
            vlm_results.append(_assemble_vlm_output(intermediates[i], analysis))

    workflow.logger.info(
        f"Phase 2 complete: {len(vlm_results)}/{total} assembled"
        + (f" ({failed_count} failed)" if failed_count else "")
    )
    max_tolerated = max(1, int(total * cfg.VLM_FAILURE_TOLERANCE))
    if failed_count > max_tolerated:
        raise RuntimeError(f"VLM summary failed for {failed_count}/{total} elements (tolerance: {max_tolerated})")
    elif failed_count > 0:
        workflow.logger.warning(
            f"VLM: {failed_count}/{total} summary elements failed "
            f"(within tolerance of {max_tolerated}), proceeding with partial results"
        )
    return vlm_results


# ---------------------------------------------------------------------------
# Public entry point (same signature as before)
# ---------------------------------------------------------------------------


async def process_vlm_batches(
    vlm_inputs: list[VLMWorkflowInput],
) -> list[VLMWorkflowOutput]:
    """Two-phase VLM processing: extract+describe then summarize+assemble.

    Same signature and return type as before — ``SingleDocumentWorkflow``
    is unaffected.
    """
    if not vlm_inputs:
        return []

    total = len(vlm_inputs)
    workflow.logger.info(f"Starting two-phase VLM processing for {total} elements")

    # Phase 1: Extract + Describe (VLM, needs image bytes)
    intermediates = await _run_extract_describe(vlm_inputs)

    if not intermediates:
        workflow.logger.warning("No successful extract+describe results; skipping Phase 2")
        return []

    # Phase 2: Summarize + Assemble (LLM, text-only)
    vlm_results = await _summarize_and_assemble(intermediates)

    workflow.logger.info(f"VLM processing complete: {len(vlm_results)}/{total} succeeded")
    return vlm_results
