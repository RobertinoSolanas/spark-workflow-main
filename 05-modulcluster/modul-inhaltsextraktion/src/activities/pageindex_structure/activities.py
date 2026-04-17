# src/activities/pageindex_structure/activities.py
"""
Temporal activities, I/O models, and orchestration helpers for PageIndex structure extraction.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.activities.dms_activities import DmsFileInfo
from src.config import get_config
from src.models.model_manager import SelfHostedConfig
from src.utils.dms_utils import (
    DmsUploadInput,
    ListFilesInput,
    download_file,
    list_files,
    upload_file,
)
from src.workflows.pageindex_structure.output_format import (
    DocumentStructureOutputFormat,
)

from .summarization import (
    _STRUCTURE_LLM_CONFIG,
    generate_summaries_for_structure_md,
)
from .tree_builder import (
    add_page_information,
    build_tree_from_nodes,
    extract_node_text_content,
    extract_nodes_from_markdown,
    format_structure,
    tree_thinning_for_index,
    update_node_list_with_text_token_count,
    write_node_id,
)

logger = logging.getLogger("uvicorn")


# ---------------------------------------------------------------------------
# I/O models
# ---------------------------------------------------------------------------


class CreatePageindexJsonInput(BaseModel):
    json_source_id: UUID
    json_filename: str
    project_id: UUID


class CreatePageindexJsonOutput(BaseModel):
    json_created_id: UUID
    filename: str


# ---------------------------------------------------------------------------
# Orchestration helpers
# ---------------------------------------------------------------------------


async def md_to_tree(
    markdown_content: str,
    md_path: str,
    llm_config: SelfHostedConfig,
    min_token_threshold: int | None = None,
    summary_token_threshold: int | None = None,
) -> dict[str, Any]:
    """Convert markdown content into a hierarchical tree with LLM-generated summaries."""
    logger.info("Extracting nodes from markdown...")
    node_list, markdown_lines = extract_nodes_from_markdown(markdown_content)

    logger.info("Extracting text content from nodes...")
    nodes_with_content = extract_node_text_content(node_list, markdown_lines)

    if min_token_threshold:
        nodes_with_content = update_node_list_with_text_token_count(nodes_with_content)
        logger.info("Thinning nodes...")
        nodes_with_content = tree_thinning_for_index(nodes_with_content, min_token_threshold)

    logger.info("Building tree from nodes...")
    tree_structure = build_tree_from_nodes(nodes_with_content)

    logger.info("Writing node id...")
    write_node_id(tree_structure)

    logger.info("Formatting tree structure...")
    tree_structure = format_structure(
        tree_structure,
        order=[
            "title",
            "node_id",
            "summary",
            "prefix_summary",
            "text",
            "line_num",
            "nodes",
        ],
    )

    logger.info("Generating summaries for each node...")
    tree_structure = await generate_summaries_for_structure_md(
        tree_structure,
        summary_token_threshold=summary_token_threshold or 200,
        llm_config=llm_config,
    )

    return {
        "doc_name": os.path.splitext(os.path.basename(md_path))[0],
        "structure": tree_structure,
    }


async def create_pageindex_structure(
    md_path: str,
    markdown_content: str,
    thinning_threshold: int | None = None,
    summary_token_threshold: int = 200,
) -> dict[str, Any]:
    toc_data = await md_to_tree(
        markdown_content=markdown_content,
        md_path=md_path,
        llm_config=_STRUCTURE_LLM_CONFIG,
        min_token_threshold=thinning_threshold,
        summary_token_threshold=summary_token_threshold,
    )

    toc_with_page_number = add_page_information(toc_data, markdown_content)

    return toc_with_page_number


# ---------------------------------------------------------------------------
# Activity definitions
# ---------------------------------------------------------------------------


@activity.defn(name="get_structure_list_valid_files")
async def _get_structure_list_valid_files(project_id: UUID) -> list[DmsFileInfo]:
    """List all *_processed.json files for a project from DMS.

    Paginates through all pages to ensure no files are missed.
    """
    page_size = 500
    page = 1
    results: list[DmsFileInfo] = []

    while True:
        batch = await list_files(
            ListFilesInput(
                project_id=project_id,
                file_type="content_extraction",
                page=page,
                page_size=page_size,
            )
        )

        for f in batch:
            if f.filename.endswith("_processed.json"):
                results.append(DmsFileInfo.from_file_object(f))

        if len(batch) < page_size:
            break
        page += 1

    activity.logger.info(
        "Found %d _processed.json files for project %s",
        len(results),
        project_id,
    )
    return results


@activity.defn(name="create_pageindex_json")
async def _create_pageindex_json(
    input: CreatePageindexJsonInput,
) -> CreatePageindexJsonOutput:
    """Download a *_processed.json, build hierarchical structure with summaries, upload *_structure.json."""
    if not input.json_filename.endswith("_processed.json"):
        raise ValueError(f"Expected filename ending with '_processed.json', got: {input.json_filename}")

    processed_json_bytes = await download_file(input.json_source_id)
    processed_json_data = json.loads(processed_json_bytes)
    markdown_content = processed_json_data.get("markdown_content", "")
    md_path = input.json_filename.replace(".json", ".md")

    map_structure = await create_pageindex_structure(
        md_path,
        markdown_content,
        summary_token_threshold=200,
    )

    meta_data = processed_json_data.get("metadata")
    structure_output = DocumentStructureOutputFormat(
        doc_name=map_structure["doc_name"],
        project_id=meta_data.get("project_id", ""),
        document_id=meta_data.get("document_id", ""),
        source_file_id=meta_data.get("source_file_id", ""),
        structure=map_structure.get("structure"),
    )

    structure_filename = input.json_filename.replace("_processed.json", "_structure.json")
    structure_json_str = structure_output.model_dump_json(indent=2)
    structure_file_bytes = structure_json_str.encode("utf-8")
    file_obj = await upload_file(
        DmsUploadInput(
            data=structure_file_bytes,
            filename=structure_filename,
            project_id=input.project_id,
            file_type="content_extraction",
            content_type="application/json",
        )
    )

    activity.logger.info(f"Created structure file '{structure_filename}' (id={file_obj.id})")

    return CreatePageindexJsonOutput(
        json_created_id=str(file_obj.id),
        filename=structure_filename,
    )


# ---------------------------------------------------------------------------
# Public workflow wrappers (standard pattern)
# ---------------------------------------------------------------------------


async def get_structure_list_valid_files(project_id: UUID) -> list[DmsFileInfo]:
    """Workflow wrapper: list valid processed JSON files for a project."""
    return await workflow.execute_activity(
        _get_structure_list_valid_files,
        project_id,
        start_to_close_timeout=timedelta(minutes=5),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_STORAGE_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=10),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=60),
        ),
    )


async def create_pageindex_json(
    input: CreatePageindexJsonInput,
) -> CreatePageindexJsonOutput:
    """Workflow wrapper: create pageindex structure JSON for a single file."""
    return await workflow.execute_activity(
        _create_pageindex_json,
        input,
        start_to_close_timeout=timedelta(hours=1),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_LLM_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=10),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=60),
        ),
    )
