# src/workflows/helpers/base_metadata_extractor.py
"""
Base metadata extraction helper for SingleDocumentWorkflow.

Handles extraction of base metadata from priority documents using
multi-chunk evidence gathering and LLM consolidation.
"""

import asyncio
import json
from datetime import timedelta
from typing import Any

from pydantic import BaseModel
from temporal.workflows.inhaltsextraktion.types import BaseMetadata
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.activities.llm_invoke import (
    LlmInvokeInput,
    llm_invoke_structured,
    llm_invoke_structured_direct,
)
from src.config import get_config
from src.models.model_manager import SelfHostedConfig
from src.workflows.base_metadata.output_format import (
    BaseMetadataWithEvidence,
    LlmConsolidatedMetadata,
)
from src.workflows.base_metadata.prompt import (
    CONSOLIDATE_EVIDENCE_SYSTEM_PROMPT,
    CONSOLIDATE_EVIDENCE_USER_TEMPLATE,
    GATHER_EVIDENCE_SYSTEM_PROMPT,
    GATHER_EVIDENCE_USER_TEMPLATE,
)

# --- Activity Input Models ---


class ConsolidateMetadataInput(BaseModel):
    all_evidence: list[dict[str, Any]]
    project_id: str


# --- Activity Definitions ---


@activity.defn(name="consolidate_base_metadata")
async def _consolidate_base_metadata(
    input: ConsolidateMetadataInput,
) -> BaseMetadata:
    """
    Consolidate evidence from multiple chunks into final metadata.

    This is an activity because:
    1. json.dumps on large evidence lists is CPU-intensive
    2. Keeps all consolidation logic in one place

    Uses llm_invoke_structured_direct since we're in activity context.
    """
    if not input.all_evidence:
        return BaseMetadata(application_id=input.project_id)

    llm_config: SelfHostedConfig = {
        "provider": "self_hosted",
        "model_name": "metadata",
    }

    try:
        activity.logger.info(f"Consolidating evidence from {len(input.all_evidence)} chunks...")

        # JSON serialization now happens in activity context (not workflow thread)
        evidence_json_str = json.dumps(input.all_evidence, ensure_ascii=False)

        # Use direct LLM call (we're in activity context, can't use activity wrapper)
        llm_output = await llm_invoke_structured_direct(
            input=LlmInvokeInput(
                llm_config=llm_config,
                prompt_template=CONSOLIDATE_EVIDENCE_USER_TEMPLATE,
                input_dict={"evidence_list_json": evidence_json_str},
                agent_name="base_metadata_consolidator",
                system_prompt=CONSOLIDATE_EVIDENCE_SYSTEM_PROMPT,
            ),
            output_class=LlmConsolidatedMetadata,
        )

        consolidated_data = llm_output.model_dump()
        consolidated_data["application_id"] = input.project_id

        return BaseMetadata(**consolidated_data)
    except Exception as e:
        activity.logger.error(f"Failed to consolidate metadata evidence: {e}")
        return BaseMetadata(application_id=input.project_id)


# --- Workflow Wrappers ---


async def consolidate_base_metadata(
    all_evidence: list[dict[str, Any]],
    project_id: str,
) -> BaseMetadata:
    """Workflow wrapper for consolidate_base_metadata activity."""
    return await workflow.execute_activity(
        _consolidate_base_metadata,
        ConsolidateMetadataInput(all_evidence=all_evidence, project_id=project_id),
        start_to_close_timeout=timedelta(minutes=5),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_LLM_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2,
            maximum_interval=timedelta(seconds=60),
        ),
    )


# --- Workflow Helper Functions ---


async def extract_base_metadata(
    final_markdown: str,
    project_id: str,
) -> BaseMetadata:
    """
    Extract base metadata from a priority document.

    This function:
    1. Splits markdown into chunks
    2. Gathers evidence from each chunk in parallel (via activities)
    3. Consolidates the evidence into final metadata (via activity)

    Args:
        final_markdown: The markdown content to extract metadata from.
        project_id: The project ID to use as the application_id in the metadata.
    """
    cfg = get_config()
    total_limit = cfg.BASE_METADATA_TOTAL_LIMIT
    chunk_size = cfg.BASE_METADATA_CHUNK_SIZE

    md_content = final_markdown[:total_limit]

    # Gather evidence from chunks
    all_evidence = await _gather_evidence_from_chunks(md_content, chunk_size)

    if not all_evidence:
        workflow.logger.warning("No evidence was gathered from any document chunks.")
        return BaseMetadata(application_id=project_id)

    # Consolidate evidence via activity (avoids json.dumps blocking workflow thread)
    return await consolidate_base_metadata(all_evidence, project_id)


async def _gather_evidence_from_chunks(
    markdown: str,
    chunk_size: int,
) -> list[dict[str, Any]]:
    """
    Gather metadata evidence from document chunks in parallel.
    """
    llm_config: SelfHostedConfig = {
        "provider": "self_hosted",
        "model_name": "metadata",
    }

    gather_tasks = []
    for i in range(0, len(markdown), chunk_size):
        content_snippet = markdown[i : i + chunk_size]
        if not content_snippet:
            break

        gather_tasks.append(
            llm_invoke_structured(
                input=LlmInvokeInput(
                    llm_config=llm_config,
                    prompt_template=GATHER_EVIDENCE_USER_TEMPLATE,
                    input_dict={"markdown_content": content_snippet},
                    agent_name=f"base_metadata_gatherer_{i // chunk_size}",
                    system_prompt=GATHER_EVIDENCE_SYSTEM_PROMPT,
                ),
                output_class=BaseMetadataWithEvidence,
            )
        )

    results = await asyncio.gather(*gather_tasks, return_exceptions=True)

    all_evidence = []
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            workflow.logger.error(f"Failed to extract evidence from chunk {i}: {result}")
        elif result and result.model_dump(exclude_none=True):
            all_evidence.append(result.model_dump())

    return all_evidence
