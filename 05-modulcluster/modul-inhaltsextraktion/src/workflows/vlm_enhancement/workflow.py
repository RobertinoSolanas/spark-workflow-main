"""
Temporal workflow for VLM (Visual Language Model) processing of a single visual element.

This workflow handles the extract+describe phase only.  The summarize+assemble
phase is handled by the batch processor so that all LLM summary calls can run
as a concurrent wave of activities once the image-dependent VLM work is done.
"""

import asyncio
from typing import Any
from uuid import uuid4

from temporalio import workflow
from temporalio.client import Client, WorkflowHandle
from temporalio.exceptions import ApplicationError

from src.activities.vlm_invoke import (
    vlm_describe_image,
    vlm_extract_content,
)
from src.config import get_config
from src.utils.text_utils import (
    detect_hallucination_loop,
    truncate_hallucinated_content,
)
from src.workflows.vlm_enhancement.output_format import (
    VLMExtractDescribeOutput,
    VLMWorkflowInput,
)

vlm_workflow_id = "vlm-enhancement"


async def start_vlm_enhancement(client: Client, input: VLMWorkflowInput) -> WorkflowHandle[Any, Any]:
    from src.env import ENV

    return await client.start_workflow(
        vlm_workflow_id,
        input,
        id=str(uuid4()),
        task_queue=ENV.TEMPORAL_TASK_QUEUE,
    )


async def execute_vlm_enhancement(client: Client, input: VLMWorkflowInput) -> VLMExtractDescribeOutput:
    from src.env import ENV

    return await client.execute_workflow(
        vlm_workflow_id,
        input,
        id=str(uuid4()),
        task_queue=ENV.TEMPORAL_TASK_QUEUE,
    )


@workflow.defn(name=vlm_workflow_id)
class VLMWorkflow:
    """
    Workflow to extract and describe a single visual element (image or table) using VLM.

    Returns an intermediate ``VLMExtractDescribeOutput`` (no image bytes) so that
    the downstream summary call can be batched across all elements.
    """

    @workflow.run
    async def run(self, input: VLMWorkflowInput) -> VLMExtractDescribeOutput:
        """Executes VLM extract+describe for a single visual element."""
        cfg = get_config()

        # For tables with pre-extracted HTML (Docling pipeline),
        # skip VLM extraction entirely — structured extraction is more accurate
        # than VLM image-based extraction
        if input.element_type == "table" and input.raw_html:
            workflow.logger.info(f"Using pre-extracted HTML for table {input.image_ref} (skipping VLM extraction)")
            extraction_result = input.raw_html
            # Only need description call (no extraction needed for pre-extracted HTML)
            description_result = await vlm_describe_image(input.image_data, input.image_ref)
            extraction_hallucinated_by_size = False
        else:
            # Run extraction and description in parallel (independent operations)
            extraction_result, description_result = await asyncio.gather(
                vlm_extract_content(input.image_data, input.image_ref, input.element_type),
                vlm_describe_image(input.image_data, input.image_ref),
            )

            # Check for hallucination loops in extraction (catches 3GB+ outputs from technical drawings)
            extraction_hallucinated_by_size = detect_hallucination_loop(
                extraction_result, max_length=cfg.HALLUCINATION_MAX_LENGTH
            )
            if extraction_hallucinated_by_size:
                workflow.logger.warning(
                    f"Hallucination loop detected in extraction for {input.image_ref} "
                    f"(length: {len(extraction_result):,} chars). Truncating content."
                )
                extraction_result = truncate_hallucinated_content(
                    extraction_result, max_length=cfg.HALLUCINATION_TRUNCATE_LENGTH
                )

            # Fallback: If VLM returns empty/error/unusable for tables, use pipeline's table_body
            if input.element_type == "table" and input.raw_html:
                stripped = extraction_result.strip()
                is_unusable = (
                    not stripped
                    or stripped.startswith("[No table content")
                    or stripped.startswith("[No content extracted")
                    or stripped.startswith("[Error")
                    or (stripped.startswith("![") and stripped.endswith(")") and "<table" not in stripped.lower())
                )
                if is_unusable:
                    workflow.logger.info(
                        f"Using pipeline table_body as fallback for {input.image_ref} "
                        f"(VLM returned unusable: {extraction_result[:80]}...)"
                    )
                    extraction_result = input.raw_html

        # Check for hallucination loops in description
        description_hallucinated_by_size = detect_hallucination_loop(
            description_result, max_length=cfg.HALLUCINATION_MAX_LENGTH
        )
        if description_hallucinated_by_size:
            workflow.logger.warning(
                f"Hallucination loop detected in description for {input.image_ref} "
                f"(length: {len(description_result):,} chars). Truncating content."
            )
            description_result = truncate_hallucinated_content(
                description_result, max_length=cfg.HALLUCINATION_TRUNCATE_LENGTH
            )

        # Check if VLM could not see the image at all.
        # Both extraction and description are empty (VLM returned null/empty for both).
        both_empty = not extraction_result.strip() and not description_result.strip()
        if both_empty:
            raise ApplicationError(
                f"VLM could not see image for {input.image_ref}. "
                f"Extraction: {extraction_result[:120]!r} | "
                f"Description: {description_result[:120]!r}",
                type="NoImageError",
                non_retryable=True,
            )

        return VLMExtractDescribeOutput(
            image_ref=input.image_ref,
            element_type=input.element_type,
            extraction_result=extraction_result,
            description_result=description_result,
            context_text=input.context_text,
            full_tag=input.full_tag,
            raw_html=input.raw_html,
            extraction_hallucinated_by_size=extraction_hallucinated_by_size,
            description_hallucinated_by_size=description_hallucinated_by_size,
        )
