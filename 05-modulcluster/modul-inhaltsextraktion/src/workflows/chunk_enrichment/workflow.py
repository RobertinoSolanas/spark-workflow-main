# src/workflows/chunk_enrichment/workflow.py
"""
Temporal workflow for orchestrating chunk enrichment.

Simplified architecture following shared enrichment pattern:
- Input: List of Chunk objects directly
- Output: List of enriched Chunk objects directly
- Runs child workflows in parallel, gated by shared semaphores
- No intermediate DMS file storage

This workflow runs multiple enrichment workflows in parallel:
1. Schwerpunktthema classification
2. Species/Scale extraction
3. Hypothetical questions generation
"""

import asyncio
from collections.abc import Coroutine
from datetime import timedelta
from typing import Any

from pydantic import BaseModel
from temporalio import workflow

from src.config import snapshot_config
from src.schemas import Chunk
from src.workflows.hypothetical_questions.workflow import (
    HypotheticalQuestionsWorkflow,
    HypotheticalQuestionsWorkflowInput,
    HypotheticalQuestionsWorkflowOutput,
)
from src.workflows.schwerpunkt.workflow import (
    SchwerpunktWorkflow,
    SchwerpunktWorkflowInput,
    SchwerpunktWorkflowOutput,
)
from src.workflows.species_scale.workflow import (
    SpeciesScaleWorkflow,
    SpeciesScaleWorkflowInput,
    SpeciesScaleWorkflowOutput,
)


class ChunkEnrichmentWorkflowInput(BaseModel):
    """Input for the chunk enrichment orchestration workflow."""

    chunks: list[Chunk]


class ChunkEnrichmentWorkflowOutput(BaseModel):
    """Output from the chunk enrichment orchestration workflow."""

    chunks: list[Chunk]


chunk_enrichment_workflow_id = "chunk-metadata-workflow"


def _merge_chunk_metadata(  # noqa: C901
    original_chunks: list[Chunk],
    schwerpunkt_chunks: list[Chunk] | None,
    species_scale_chunks: list[Chunk] | None,
    hypo_questions_chunks: list[Chunk] | None,
) -> list[Chunk]:
    """
    Merges metadata from parallel workflow results into a single list of chunks.

    Each child workflow enriches chunks with its specific metadata field.
    This function combines all metadata fields into the final chunks.
    """
    # Create lookup maps by chunk_id for each enrichment result
    schwerpunkt_map: dict[str, Chunk] = {}
    species_scale_map: dict[str, Chunk] = {}
    hypo_questions_map: dict[str, Chunk] = {}

    if schwerpunkt_chunks:
        schwerpunkt_map = {str(c.chunk_id): c for c in schwerpunkt_chunks}
    if species_scale_chunks:
        species_scale_map = {str(c.chunk_id): c for c in species_scale_chunks}
    if hypo_questions_chunks:
        hypo_questions_map = {str(c.chunk_id): c for c in hypo_questions_chunks}

    merged_chunks = []
    for chunk in original_chunks:
        chunk_id = str(chunk.chunk_id)
        merged_metadata = {**chunk.metadata}

        # Merge schwerpunktthema
        if chunk_id in schwerpunkt_map:
            enriched = schwerpunkt_map[chunk_id]
            if "focus_topic" in enriched.metadata:
                merged_metadata["focus_topic"] = enriched.metadata["focus_topic"]

        # Merge species/scale fields
        if chunk_id in species_scale_map:
            enriched = species_scale_map[chunk_id]
            for field_name in [
                "wildlife_mentioned",
                "plant_species_mentioned",
                "wildlife_species",
                "plant_species",
                "map_scale",
            ]:
                if field_name in enriched.metadata:
                    merged_metadata[field_name] = enriched.metadata[field_name]

        # Merge hypothetical questions
        if chunk_id in hypo_questions_map:
            enriched = hypo_questions_map[chunk_id]
            if "hypothetical_questions" in enriched.metadata:
                merged_metadata["hypothetical_questions"] = enriched.metadata["hypothetical_questions"]

        # Update sub_chunks with merged metadata as well
        updated_sub_chunks = []
        for sub_chunk in chunk.sub_chunks:
            sub_metadata = {**sub_chunk.metadata}
            # Apply same metadata fields to sub_chunks
            if "focus_topic" in merged_metadata:
                sub_metadata["focus_topic"] = merged_metadata["focus_topic"]
            for field_name in [
                "wildlife_mentioned",
                "plant_species_mentioned",
                "wildlife_species",
                "plant_species",
                "map_scale",
            ]:
                if field_name in merged_metadata:
                    sub_metadata[field_name] = merged_metadata[field_name]
            if "hypothetical_questions" in merged_metadata:
                sub_metadata["hypothetical_questions"] = merged_metadata["hypothetical_questions"]
            updated_sub_chunks.append(sub_chunk.model_copy(update={"metadata": sub_metadata}))

        merged_chunk = chunk.model_copy(update={"metadata": merged_metadata, "sub_chunks": updated_sub_chunks})
        merged_chunks.append(merged_chunk)

    return merged_chunks


@workflow.defn(name=chunk_enrichment_workflow_id)
class ChunkEnrichmentWorkflow:
    """
    Orchestration workflow that runs all chunk enrichment workflows in parallel.

    Runs:
    - SchwerpunktWorkflow (if enabled)
    - SpeciesScaleWorkflow (if enabled)
    - HypotheticalQuestionsWorkflow (if enabled)

    All workflows process the same input chunks independently and in parallel.
    Their results are then merged into a single enriched chunks list.
    """

    @workflow.run
    async def run(self, input: ChunkEnrichmentWorkflowInput) -> ChunkEnrichmentWorkflowOutput:
        """
        Orchestrates parallel chunk enrichment.

        Runs all enrichment workflows concurrently. Each workflow internally
        uses shared semaphores to gate LLM request concurrency.
        """
        cfg = snapshot_config()
        workflow.logger.info(f"Starting CHUNK METADATA orchestration for {len(input.chunks)} chunks")

        if not input.chunks:
            return ChunkEnrichmentWorkflowOutput(chunks=[])

        # Track results from each workflow
        schwerpunkt_result: SchwerpunktWorkflowOutput | None = None
        species_scale_result: SpeciesScaleWorkflowOutput | None = None
        hypo_questions_result: HypotheticalQuestionsWorkflowOutput | None = None

        # Launch all enabled enrichment workflows in parallel.
        # Failures propagate — the document retry loop in
        # ProcessDocumentsWorkflow handles transient errors.
        async def run_schwerpunkt() -> SchwerpunktWorkflowOutput:
            """Run topic classification sub-workflow."""
            result = await workflow.execute_child_workflow(
                SchwerpunktWorkflow.run,
                arg=SchwerpunktWorkflowInput(chunks=input.chunks),
                id=f"schwerpunkt-{workflow.info().workflow_id}",
                task_queue=workflow.info().task_queue,
                task_timeout=timedelta(seconds=60),
            )
            workflow.logger.info("Schwerpunkt workflow completed")
            return result

        async def run_species_scale() -> SpeciesScaleWorkflowOutput:
            """Run species and scale extraction sub-workflow."""
            result = await workflow.execute_child_workflow(
                SpeciesScaleWorkflow.run,
                arg=SpeciesScaleWorkflowInput(chunks=input.chunks),
                id=f"species-scale-{workflow.info().workflow_id}",
                task_queue=workflow.info().task_queue,
                task_timeout=timedelta(seconds=60),
            )
            workflow.logger.info("Species/Scale workflow completed")
            return result

        async def run_hypo_questions() -> HypotheticalQuestionsWorkflowOutput:
            """Run hypothetical questions generation sub-workflow."""
            result = await workflow.execute_child_workflow(
                HypotheticalQuestionsWorkflow.run,
                arg=HypotheticalQuestionsWorkflowInput(chunks=input.chunks),
                id=f"hypo-questions-{workflow.info().workflow_id}",
                task_queue=workflow.info().task_queue,
                task_timeout=timedelta(seconds=60),
            )
            workflow.logger.info("Hypothetical Questions workflow completed")
            return result

        # Build list of coroutines for enabled workflows
        tasks: list[Coroutine[Any, Any, Any]] = []
        task_names: list[str] = []

        if cfg.ENABLE_SCHWERPUNKTTHEMA_EXTRACTION:
            workflow.logger.info("Starting Schwerpunkt workflow")
            tasks.append(run_schwerpunkt())
            task_names.append("schwerpunkt")

        if cfg.ENABLE_SPECIES_SCALE_EXTRACTION:
            workflow.logger.info("Starting Species/Scale workflow")
            tasks.append(run_species_scale())
            task_names.append("species_scale")

        if cfg.ENABLE_HYPOTHETICAL_QUESTIONS:
            workflow.logger.info("Starting Hypothetical Questions workflow")
            tasks.append(run_hypo_questions())
            task_names.append("hypo_questions")

        # Run all workflows in parallel
        results = await asyncio.gather(*tasks)

        # Map results back to their workflow outputs
        for name, result in zip(task_names, results, strict=False):
            if name == "schwerpunkt" and isinstance(result, SchwerpunktWorkflowOutput):
                schwerpunkt_result = result
            elif name == "species_scale" and isinstance(result, SpeciesScaleWorkflowOutput):
                species_scale_result = result
            elif name == "hypo_questions" and isinstance(result, HypotheticalQuestionsWorkflowOutput):
                hypo_questions_result = result

        # Merge all results
        workflow.logger.info("Merging enrichment results")

        merged_chunks = _merge_chunk_metadata(
            original_chunks=input.chunks,
            schwerpunkt_chunks=schwerpunkt_result.chunks if schwerpunkt_result else None,
            species_scale_chunks=species_scale_result.chunks if species_scale_result else None,
            hypo_questions_chunks=hypo_questions_result.chunks if hypo_questions_result else None,
        )

        workflow.logger.info(f"Chunk metadata extraction completed for {len(merged_chunks)} chunks")

        return ChunkEnrichmentWorkflowOutput(chunks=merged_chunks)
