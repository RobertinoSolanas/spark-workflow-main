# src/activities/chunk_enrichment.py
"""
Temporal activities for chunk enrichment orchestration.

This activity merges results from all parallel enrichment workflows
(Schwerpunkt, SpeciesScale, HypotheticalQuestions) into a single chunks file.
"""

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.config import get_config
from src.schemas import Chunk
from src.utils.dms_utils import (
    DmsUploadInput,
    delete_file,
    download_file,
    upload_file,
)
from src.workflows.schwerpunkt.output_format import SchwerpunktMetadata
from src.workflows.species_scale.output_format import SpeciesAndScaleResult


class _HypotheticalQuestionsMetadata(BaseModel):
    hypothetical_questions: list[str] = []


def _parse_chunks(raw_bytes: bytes) -> list[Chunk]:
    """Parse DMS JSON bytes into validated Chunk models."""
    return [Chunk(**item) for item in json.loads(raw_bytes)]


def _extract_schwerpunkt_metadata(chunks: list[Chunk]) -> dict[int, dict[str, Any]]:
    """Extract focus_topic from schwerpunkt-enriched chunks."""
    metadata_map: dict[int, dict[str, Any]] = {}
    for i, chunk in enumerate(chunks):
        try:
            meta = SchwerpunktMetadata.model_validate(chunk.metadata)
            metadata_map[i] = meta.model_dump()
        except ValidationError:
            pass
    return metadata_map


def _extract_species_scale_metadata(chunks: list[Chunk]) -> dict[int, dict[str, Any]]:
    """Extract species/scale fields from enriched chunks."""
    metadata_map: dict[int, dict[str, Any]] = {}
    for i, chunk in enumerate(chunks):
        try:
            meta = SpeciesAndScaleResult.model_validate(chunk.metadata)
            dumped = meta.model_dump(exclude_none=True)
            if dumped:
                metadata_map[i] = dumped
        except ValidationError:
            pass
    return metadata_map


def _extract_hypo_questions_metadata(chunks: list[Chunk]) -> dict[int, dict[str, Any]]:
    """Extract hypothetical_questions from enriched chunks."""
    metadata_map: dict[int, dict[str, Any]] = {}
    for i, chunk in enumerate(chunks):
        try:
            meta = _HypotheticalQuestionsMetadata.model_validate(chunk.metadata)
            if meta.hypothetical_questions:
                metadata_map[i] = meta.model_dump(include={"hypothetical_questions"})
        except ValidationError:
            pass
    return metadata_map


@dataclass
class MergeEnrichmentInput:
    """Activity input for merging all enrichment results."""

    original_chunks_file_id: str
    schwerpunkt_chunks_file_id: str | None
    species_scale_chunks_file_id: str | None
    hypo_questions_chunks_file_id: str | None
    project_id: str
    doc_stem: str


@activity.defn(name="merge_all_enrichment_results")
async def _merge_all_enrichment_results(input: MergeEnrichmentInput) -> str:  # noqa: C901
    """
    Merges all enrichment results from parallel workflows into a final chunks file.

    Downloads each enrichment result, validates it as a list of Chunks,
    extracts the relevant metadata fields, merges them into the original
    chunks, and uploads the combined result.

    DMS download failures are not caught — they propagate so Temporal
    retries the activity (transient DMS outages are recovered automatically).
    """
    stem = Path(input.doc_stem).name

    activity.logger.info("Merging enrichment results from parallel workflows")

    # 1. Download original chunks as baseline
    chunks = _parse_chunks(await download_file(input.original_chunks_file_id))

    sources: list[str] = []

    # 2. Download and extract metadata from each enrichment result
    schwerpunkt_metadata_map: dict[int, dict[str, Any]] = {}
    if input.schwerpunkt_chunks_file_id:
        schwerpunkt_chunks = _parse_chunks(await download_file(input.schwerpunkt_chunks_file_id))
        schwerpunkt_metadata_map = _extract_schwerpunkt_metadata(schwerpunkt_chunks)
        sources.append("schwerpunkt")
        activity.logger.info(f"Loaded schwerpunktthema for {len(schwerpunkt_metadata_map)} chunks")

    species_scale_metadata_map: dict[int, dict[str, Any]] = {}
    if input.species_scale_chunks_file_id:
        species_chunks = _parse_chunks(await download_file(input.species_scale_chunks_file_id))
        species_scale_metadata_map = _extract_species_scale_metadata(species_chunks)
        sources.append("species_scale")
        activity.logger.info(f"Loaded species/scale for {len(species_scale_metadata_map)} chunks")

    hypo_metadata_map: dict[int, dict[str, Any]] = {}
    if input.hypo_questions_chunks_file_id:
        hypo_chunks = _parse_chunks(await download_file(input.hypo_questions_chunks_file_id))
        hypo_metadata_map = _extract_hypo_questions_metadata(hypo_chunks)
        sources.append("hypo_questions")
        activity.logger.info(f"Loaded hypothetical questions for {len(hypo_metadata_map)} chunks")

    # 3. Merge all metadata into chunks
    new_chunks = []
    for i, chunk in enumerate(chunks):
        merged_metadata = {**chunk.metadata}

        if i in schwerpunkt_metadata_map:
            merged_metadata.update(schwerpunkt_metadata_map[i])
        if i in species_scale_metadata_map:
            merged_metadata.update(species_scale_metadata_map[i])
        if i in hypo_metadata_map:
            merged_metadata.update(hypo_metadata_map[i])

        updated_sub_chunks = []
        for sub_chunk in chunk.sub_chunks:
            sub_metadata = {**sub_chunk.metadata}
            if i in schwerpunkt_metadata_map:
                sub_metadata.update(schwerpunkt_metadata_map[i])
            if i in species_scale_metadata_map:
                sub_metadata.update(species_scale_metadata_map[i])
            if i in hypo_metadata_map:
                sub_metadata.update(hypo_metadata_map[i])
            updated_sub_chunks.append(sub_chunk.model_copy(update={"metadata": sub_metadata}))

        new_chunk = chunk.model_copy(update={"metadata": merged_metadata, "sub_chunks": updated_sub_chunks})
        new_chunks.append(new_chunk)

    activity.logger.info(f"Merged metadata from sources: {sources} into {len(new_chunks)} chunks")

    # 4. Upload merged chunks to DMS
    def default(obj: Any) -> Any:
        if isinstance(obj, UUID):
            return str(obj)
        raise TypeError

    chunks_json_str = json.dumps([c.model_dump() for c in new_chunks], indent=2, default=default)

    merged_chunks_file = await upload_file(
        DmsUploadInput(
            data=chunks_json_str.encode("utf-8"),
            filename=f"{input.doc_stem}/{stem}_chunks_enriched.json",
            project_id=UUID(input.project_id),
            file_type="content_extraction",
            content_type="application/json",
        )
    )

    activity.logger.info(f"Uploaded merged chunks to DMS: {merged_chunks_file.id}")

    # 5. Clean up intermediate enrichment files (but keep original)
    files_to_delete = [
        f
        for f in [
            input.schwerpunkt_chunks_file_id,
            input.species_scale_chunks_file_id,
            input.hypo_questions_chunks_file_id,
        ]
        if f and f != input.original_chunks_file_id
    ]

    for file_id in files_to_delete:
        try:
            await delete_file(UUID(file_id))
            activity.logger.debug(f"Deleted intermediate file: {file_id}")
        except Exception as e:
            activity.logger.warning(f"Failed to delete intermediate file {file_id}: {e}")

    return str(merged_chunks_file.id)


# --- Workflow Wrapper ---


async def merge_all_enrichment_results(
    original_chunks_file_id: str,
    schwerpunkt_chunks_file_id: str | None,
    species_scale_chunks_file_id: str | None,
    hypo_questions_chunks_file_id: str | None,
    project_id: str,
    doc_stem: str,
) -> str:
    """Workflow wrapper for merging all enrichment results."""
    return await workflow.execute_activity(
        _merge_all_enrichment_results,
        MergeEnrichmentInput(
            original_chunks_file_id=original_chunks_file_id,
            schwerpunkt_chunks_file_id=schwerpunkt_chunks_file_id,
            species_scale_chunks_file_id=species_scale_chunks_file_id,
            hypo_questions_chunks_file_id=hypo_questions_chunks_file_id,
            project_id=project_id,
            doc_stem=doc_stem,
        ),
        start_to_close_timeout=timedelta(minutes=10),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_PROCESSING_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=60),
        ),
    )
