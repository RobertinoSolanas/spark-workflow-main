"""
Temporal workflow for adding pageindex structure.

This workflow for a single file:

1. Loads the markdown content of a single markdown file.
2. Creates its summarized structure.
3. Saves its summarized structure to DMS with the _structure.json path.

The workflow for multiple files simply call the first one for all _processed.json
files it receives as input.
"""

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel
from temporalio import workflow
from temporalio.client import Client, WorkflowHandle
from temporalio.common import WorkflowIDReusePolicy

with workflow.unsafe.imports_passed_through():
    from src.activities.dms_activities import DmsFileInfo
    from src.activities.pageindex_structure import (
        CreatePageindexJsonInput,
        CreatePageindexJsonOutput,
        create_pageindex_json,
        get_structure_list_valid_files,
    )
    from src.env import ENV

single_file_structure_workflow_id = "single-file-structure-workflow"


@workflow.defn(name=single_file_structure_workflow_id)
class SingleFileStructureWorkflow:
    """Workflow for creating the pageindex structure for a single processed JSON file."""

    @workflow.run
    async def run(self, input: CreatePageindexJsonInput) -> CreatePageindexJsonOutput:
        return await create_pageindex_json(input)


pageindex_structure_workflow_id = "pageindex-structure-workflow"


class PageindexStructureWorkflowInput(BaseModel):
    project_id: UUID


class PageindexStructureWorkflowOutput(BaseModel):
    created_files: list[tuple[UUID, str]]


async def start_pageindex_structure(
    client: Client, input: PageindexStructureWorkflowInput
) -> WorkflowHandle[Any, Any]:
    return await client.start_workflow(
        pageindex_structure_workflow_id,
        input,
        id=str(uuid4()),
        task_queue=ENV.TEMPORAL_TASK_QUEUE,
    )


async def execute_pageindex_structure(
    client: Client, input: PageindexStructureWorkflowInput
) -> PageindexStructureWorkflowOutput:
    return await client.execute_workflow(
        pageindex_structure_workflow_id,
        input,
        id=str(uuid4()),
        task_queue=ENV.TEMPORAL_TASK_QUEUE,
    )


@workflow.defn(name=pageindex_structure_workflow_id)
class PageindexStructureWorkflow:
    """Workflow for creating the pageindex structure for all processed JSON files of a project."""

    @workflow.run
    async def run(self, input: PageindexStructureWorkflowInput) -> PageindexStructureWorkflowOutput:
        lst_file_info: list[DmsFileInfo] = await get_structure_list_valid_files(
            input.project_id,
        )

        lst_file_args: list[CreatePageindexJsonInput] = []
        for file_info in lst_file_info:
            single_file_args = CreatePageindexJsonInput(
                json_source_id=UUID(file_info.file_id),
                json_filename=file_info.filename,
                project_id=input.project_id,
            )
            lst_file_args.append(single_file_args)

        parent_wf_id = workflow.info().workflow_id

        async def run_single_document(
            idx: int, w_single_file_input: CreatePageindexJsonInput
        ) -> CreatePageindexJsonOutput:
            return await workflow.execute_child_workflow(
                SingleFileStructureWorkflow.run,
                w_single_file_input,
                id=f"single-structure-{str(w_single_file_input.json_source_id)[:8]}-{parent_wf_id[:8]}-{idx}",
                id_reuse_policy=WorkflowIDReusePolicy.TERMINATE_IF_RUNNING,
                task_queue=workflow.info().task_queue,
                task_timeout=timedelta(seconds=60),
            )

        lst_processed_files: list[tuple[UUID, str]] = []
        max_concurrency = max(3, ENV.SINGLE_DOCUMENT_WORKFLOW_CONCURRENCY)
        for i in range(0, len(lst_file_args), max_concurrency):
            batch = lst_file_args[i : i + max_concurrency]
            tasks = [run_single_document(i + j, w_arg) for j, w_arg in enumerate(batch)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for out in results:
                if isinstance(out, BaseException):
                    workflow.logger.error(f"Child workflow failed: {out}")
                    continue
                lst_processed_files.append((out.json_created_id, out.filename))

        return PageindexStructureWorkflowOutput(created_files=lst_processed_files)
