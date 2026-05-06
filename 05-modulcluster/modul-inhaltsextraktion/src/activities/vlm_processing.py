# src/activities/vlm_processing.py
"""
Activities for VLM (Visual Language Model) processing of visual elements.

This module contains higher-level VLM processing activities:
- Applying VLM results to markdown content

For core VLM API invocation, see vlm_invoke.py
"""

import re
from datetime import timedelta

from pydantic import BaseModel
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.activities.llm_invoke import LlmInvokeInput, llm_invoke_structured_direct
from src.concurrency import get_model_throttle
from src.config import get_config
from src.models.model_manager import SelfHostedConfig
from src.workflows.vlm_enhancement.output_format import (
    VlmAnalysis,
    VLMWorkflowOutput,
)
from src.workflows.vlm_enhancement.prompt import (
    VLM_LLM_SUMMARY_SYSTEM_PROMPT,
    VLM_LLM_SUMMARY_USER_TEMPLATE,
)

# --- Activity Implementations ---


class SummarizeVisualElementInput(BaseModel):
    context_text: str
    extraction_result: str
    description_result: str


@activity.defn(name="summarize_visual_element")
async def _summarize_visual_element(
    input: SummarizeVisualElementInput,
) -> VlmAnalysis:
    """
    Core logic for analyzing VLM results using an LLM to detect hallucinations
    and extract metadata like captions and footnotes.

    This uses the LLM invoke helper which now properly calls a Temporal activity.
    """
    context_text = input.context_text
    extraction_result = input.extraction_result
    description_result = input.description_result

    async with get_model_throttle("vlm_summary").acquire():
        llm_config = SelfHostedConfig(
            provider="self_hosted",
            model_name="vlm_summary",
        )

        llm_input = LlmInvokeInput(
            llm_config=llm_config,
            prompt_template=VLM_LLM_SUMMARY_USER_TEMPLATE,
            input_dict={
                "context_text": context_text,
                "extraction_result": extraction_result,
                "description_result": description_result,
            },
            agent_name="vlm.summarize_visual_element",
            system_prompt=VLM_LLM_SUMMARY_SYSTEM_PROMPT,
        )

        analysis = await llm_invoke_structured_direct(llm_input, VlmAnalysis)
        return analysis


class ApplyVlmResultsInput(BaseModel):
    vlm_results: list[VLMWorkflowOutput]
    markdown: str


@activity.defn(name="apply_vlm_results")
async def _apply_vlm_results(input: ApplyVlmResultsInput) -> str:
    """
    Apply VLM processing results to markdown content.

    Uses single-pass regex replacement to avoid O(n) full-string copies.
    Each original_content is replaced at most once (matching old replace(..., 1) semantics).
    """
    markdown = input.markdown
    vlm_results = input.vlm_results

    md_size_mb = len(markdown) / (1024 * 1024)
    if md_size_mb > 100:
        activity.logger.error(
            f"Source markdown is abnormally large ({md_size_mb:.1f} MB)! This indicates a bug earlier in the pipeline."
        )

    initial_size = len(markdown)
    max_allowed_size = max(initial_size * 10, 50 * 1024 * 1024)

    # Build replacement mapping: original_content -> replacement_block
    replacements: dict[str, str] = {}
    replacements_skipped = 0
    for vlm_output in vlm_results:
        if not vlm_output.original_content or not vlm_output.original_content.strip():
            activity.logger.warning("Skipping VLM result with empty original_content")
            replacements_skipped += 1
            continue
        if vlm_output.original_content not in replacements:
            replacements[vlm_output.original_content] = vlm_output.replacement_block

    if not replacements:
        if replacements_skipped > 0:
            activity.logger.info(f"Replacements: 0 made, {replacements_skipped} skipped")
        return markdown

    # Sort patterns longest-first to prevent partial matches
    sorted_patterns = sorted(replacements.keys(), key=len, reverse=True)

    # Compile single regex with all patterns
    combined_pattern = re.compile(
        "|".join(re.escape(p) for p in sorted_patterns),
        re.DOTALL,
    )

    # Single-pass replacement: each pattern replaced at most once
    replaced: set[str] = set()
    replacements_made = 0
    parts: list[str] = []
    last_end = 0

    for match in combined_pattern.finditer(markdown):
        matched_text = match.group(0)
        if matched_text in replaced:
            # Already replaced once — keep original text (skip this occurrence)
            continue

        replaced.add(matched_text)
        replacement = replacements[matched_text]

        parts.append(markdown[last_end : match.start()])
        parts.append(replacement)
        last_end = match.end()
        replacements_made += 1

        # Check size safety (approximate — sum of parts so far)
        current_size = sum(len(p) for p in parts) + (len(markdown) - last_end)
        if current_size > max_allowed_size:
            activity.logger.error(
                f"ABORTING: Output grew to {current_size / (1024 * 1024):.1f} MB "
                f"after {replacements_made} replacements."
            )
            break

    parts.append(markdown[last_end:])
    final_md = "".join(parts)

    not_found = len(replacements) - len(replaced)
    replacements_skipped += not_found

    if replacements_skipped > 0:
        activity.logger.info(
            f"Replacements: {replacements_made} made, {replacements_skipped} skipped"
            + (f" ({not_found} not found in markdown)" if not_found else "")
        )

    final_size_mb = len(final_md) / (1024 * 1024)
    growth_factor = len(final_md) / initial_size if initial_size > 0 else 0
    activity.logger.info(
        f"VLM replacement complete: {initial_size / (1024 * 1024):.2f} MB -> {final_size_mb:.2f} MB "
        f"({growth_factor:.1f}x growth)"
    )

    return final_md


# --- Workflow-Facing Wrappers ---


async def apply_vlm_results(
    vlm_results: list[VLMWorkflowOutput],
    markdown: str,
) -> str:
    """Workflow wrapper for apply_vlm_results activity."""
    return await workflow.execute_activity(
        _apply_vlm_results,
        ApplyVlmResultsInput(vlm_results=vlm_results, markdown=markdown),
        start_to_close_timeout=timedelta(minutes=10),
        retry_policy=RetryPolicy(maximum_attempts=get_config().TEMPORAL_PROCESSING_ACTIVITY_MAX_ATTEMPTS),
    )


async def summarize_visual_element(
    input: SummarizeVisualElementInput,
) -> VlmAnalysis:
    """Workflow wrapper to analyze and summarize VLM results."""
    return await workflow.execute_activity(
        _summarize_visual_element,
        input,
        start_to_close_timeout=timedelta(minutes=15),  # Accounts for semaphore + rate limiter queue wait time
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_VLM_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=10),
            backoff_coefficient=2,
            maximum_interval=timedelta(seconds=120),
        ),
    )
