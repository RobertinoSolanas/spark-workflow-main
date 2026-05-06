# src/activities/species_scale_extraction.py
"""
Temporal activities for Species/Scale extraction.

Architecture:
- _process_species_scale_batch: Processes a batch of chunks using batched LLM calls.
  Errors propagate for Temporal retry.
"""

import asyncio
import re
from dataclasses import dataclass
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.activities.llm_invoke import LlmInvokeInput, llm_invoke_structured_direct
from src.concurrency import get_model_throttle
from src.config import get_config
from src.models.model_manager import SelfHostedConfig
from src.schemas import Chunk
from src.workflows.species_scale.output_format import (
    BatchedSpeciesAndScaleResponse,
    SpeciesAndScaleResult,
)
from src.workflows.species_scale.prompt import (
    BATCHED_SPECIES_SCALE_SYSTEM_PROMPT,
    BATCHED_SPECIES_SCALE_USER_TEMPLATE,
)

# Module-level constants to avoid repetition
_SPECIES_SCALE_LLM_CONFIG: SelfHostedConfig = {
    "provider": "self_hosted",
    "model_name": "metadata",
}


def _clean_content_for_species_scale(content: str) -> str:
    """
    Cleans markdown content for species/scale extraction by replacing
    BILD and TABELLE blocks with only their summary tags.
    """
    from src.activities.enrichment_utils import extract_table_text

    def replace_bild(match: re.Match[str]) -> str:
        bild_content = match.group(1)
        summary_match = re.search(r"<summary>(.*?)</summary>", bild_content, re.DOTALL)
        return summary_match.group(1) if summary_match else ""

    def replace_tabelle(match: re.Match[str]) -> str:
        tabelle_content = match.group(1)
        summary_match = re.search(r"<summary>(.*?)</summary>", tabelle_content, re.DOTALL)
        if summary_match and summary_match.group(1).strip():
            return summary_match.group(1)
        return extract_table_text(tabelle_content)

    content = re.sub(r"<BILD[^>]*>(.*?)</BILD>", replace_bild, content, flags=re.DOTALL)
    content = re.sub(r"<TABELLE[^>]*>(.*?)</TABELLE>", replace_tabelle, content, flags=re.DOTALL)
    return content


async def _extract_species_scale_batch(
    chunks: list[Chunk],
) -> list[SpeciesAndScaleResult]:
    """Extract species and scale from multiple chunks in a single LLM call.

    Errors propagate to let Temporal retry the activity.
    """
    async with get_model_throttle("species_scale").acquire():
        snippet_parts = []
        for i, chunk in enumerate(chunks):
            cleaned_content = _clean_content_for_species_scale(chunk.page_content)
            snippet_parts.append(f"--- Textabschnitt {i + 1} ---\n{cleaned_content}")
        chunks_text = "\n\n".join(snippet_parts)

        result = await llm_invoke_structured_direct(
            input=LlmInvokeInput(
                llm_config=_SPECIES_SCALE_LLM_CONFIG,
                prompt_template=BATCHED_SPECIES_SCALE_USER_TEMPLATE,
                input_dict={"chunks_text": chunks_text},
                agent_name=f"species_scale_batch_{chunks[0].chunk_id}",
                system_prompt=BATCHED_SPECIES_SCALE_SYSTEM_PROMPT,
            ),
            output_class=BatchedSpeciesAndScaleResponse,
        )

        if len(result.extractions) == len(chunks):
            return result.extractions

        # Count mismatch — fall back to individual processing
        activity.logger.warning(
            f"Batched species/scale returned {len(result.extractions)} results "
            f"for {len(chunks)} chunks, falling back to individual processing"
        )

    # Process each chunk individually (outside the throttle context)
    individual_results: list[SpeciesAndScaleResult] = []
    for chunk in chunks:
        async with get_model_throttle("species_scale").acquire():
            single_result = await llm_invoke_structured_direct(
                input=LlmInvokeInput(
                    llm_config=_SPECIES_SCALE_LLM_CONFIG,
                    prompt_template=BATCHED_SPECIES_SCALE_USER_TEMPLATE,
                    input_dict={
                        "chunks_text": (
                            f"--- Textabschnitt 1 ---\n{_clean_content_for_species_scale(chunk.page_content)}"
                        )
                    },
                    agent_name=f"species_scale_individual_{chunk.chunk_id}",
                    system_prompt=BATCHED_SPECIES_SCALE_SYSTEM_PROMPT,
                ),
                output_class=BatchedSpeciesAndScaleResponse,
            )
            result = single_result.extractions[0] if single_result.extractions else SpeciesAndScaleResult()
            individual_results.append(result)
    return individual_results


@dataclass
class ProcessSpeciesScaleBatchInput:
    """Input for Species/Scale batch processing."""

    chunks: list[Chunk]


@activity.defn(name="process_species_scale_batch")
async def _process_species_scale_batch(
    input: ProcessSpeciesScaleBatchInput,
) -> list[Chunk]:
    """Processes a batch of chunks for Species/Scale extraction using batched LLM calls."""
    activity.logger.info(f"Processing batch of {len(input.chunks)} chunks for Species/Scale")

    chunks = input.chunks
    cfg = get_config()
    batch_size = cfg.SCHWERPUNKT_CLASSIFICATION_BATCH_SIZE

    sub_batches = [chunks[i : i + batch_size] for i in range(0, len(chunks), batch_size)]

    species_scale_tasks = [_extract_species_scale_batch(batch) for batch in sub_batches]

    all_results = await asyncio.gather(*species_scale_tasks)

    species_scale_results: list[SpeciesAndScaleResult] = []
    for result in all_results:
        species_scale_results.extend(result)

    enriched_chunks = []
    for j, chunk in enumerate(chunks):
        result = species_scale_results[j]
        result_dict = result.model_dump()

        updated_metadata = {**chunk.metadata, **result_dict}
        updated_sub_chunks = [
            sub_chunk.model_copy(update={"metadata": {**sub_chunk.metadata, **result_dict}})
            for sub_chunk in chunk.sub_chunks
        ]

        enriched_chunks.append(
            chunk.model_copy(update={"metadata": updated_metadata, "sub_chunks": updated_sub_chunks})
        )

    activity.logger.info(f"Batch completed: processed {len(enriched_chunks)} chunks")
    return enriched_chunks


async def process_species_scale_batch(
    input: ProcessSpeciesScaleBatchInput,
    num_concurrent_batches: int = 1,
) -> list[Chunk]:
    """Workflow wrapper for Species/Scale batch processing."""
    timeout_minutes = 10 + max(0, num_concurrent_batches - 1) * 3
    return await workflow.execute_activity(
        _process_species_scale_batch,
        input,
        start_to_close_timeout=timedelta(minutes=timeout_minutes),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_LLM_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2,
            maximum_interval=timedelta(seconds=30),
        ),
    )
